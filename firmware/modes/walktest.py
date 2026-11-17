"""Walk test: all four legs, trot gait around the baked STAND_POSE.

Diagonal pairs move together (FL+BR share phase, FR+BL are a half-cycle out).
Legs oscillate around hardware.STAND_POSE so the robot keeps body height while
stepping. Stride is clamped so peak servo commands stay inside ANGLE_RANGE.
Start-up applies the stand pose immediately; /walk/start begins the cycle;
/walk/stop returns to the hold pose. /release is the emergency floppy."""
import json
import math
import os
import signal
import sys
import time
from threading import Event, Lock, Thread

from flask import Flask, Response, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hardware  # noqa: E402


# Trot phasing: diagonals share phase so two feet always touch the ground.
GAIT_OFFSETS = {
    'front-left':  0.0,
    'back-right':  0.0,
    'front-right': math.pi,
    'back-left':   math.pi,
}

PERIOD_SECONDS = 1.6
STEP_DT = 0.05
STRIDE_RANGE = (5, 25)


def clamp(angle):
    lo, hi = hardware.ANGLE_RANGE
    return max(lo, min(hi, angle))


def leg_angles(leg_name, phase, stride):
    """Return (thigh, knee) servo commands for one leg at a given gait phase.

    Oscillates around STAND_POSE. Knee only lifts (never dips below the pose)
    using max(0, cos) so the foot clears the ground during swing but stays
    planted during stance."""
    sign = hardware.LEG_SIGNS[leg_name]
    offset = GAIT_OFFSETS[leg_name]
    thigh_osc = -stride * math.sin(phase + offset)
    knee_lift = stride * max(0.0, math.cos(phase + offset))
    thigh = sign * (hardware.STAND_POSE['thigh'] + thigh_osc)
    knee = sign * (hardware.STAND_POSE['knee'] + knee_lift)
    return clamp(thigh), clamp(knee)


def create_app(bus):
    legs = {name: hardware.resolve_leg(name) for name in hardware.LEG_SIGNS}
    positions = {}
    for channels in legs.values():
        positions[channels['thigh']] = None
        positions[channels['knee']] = None
    walk = {'thread': None, 'stop': None, 'stride': 15}
    lock = Lock()

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 2048
    app.config['WALK_BUS'] = bus
    app.config['WALK_LEGS'] = legs
    app.config['WALK_POSITIONS'] = positions
    app.config['WALK_LOCK'] = lock
    app.config['WALK_STATE'] = walk

    def is_walking():
        thread = walk['thread']
        return thread is not None and thread.is_alive()

    def snapshot():
        return {
            'walking': is_walking(),
            'stride': walk['stride'],
            'stride_range': list(STRIDE_RANGE),
            'stand_pose': dict(hardware.STAND_POSE),
            'legs': [
                {'leg': name,
                 'sign': hardware.LEG_SIGNS[name],
                 'offset_deg': int(round(math.degrees(GAIT_OFFSETS[name]))),
                 'thigh_channel': channels['thigh'],
                 'knee_channel': channels['knee'],
                 'thigh_angle': positions[channels['thigh']],
                 'knee_angle': positions[channels['knee']]}
                for name, channels in legs.items()
            ],
        }

    def write_pose(thigh_angles, knee_angles):
        for name, channels in legs.items():
            thigh = int(round(thigh_angles[name]))
            knee = int(round(knee_angles[name]))
            bus.set_angle(channels['thigh'], thigh)
            bus.set_angle(channels['knee'], knee)
            positions[channels['thigh']] = thigh
            positions[channels['knee']] = knee

    def hold_stand_pose():
        thighs = {}
        knees = {}
        for name in legs:
            sign = hardware.LEG_SIGNS[name]
            thighs[name] = clamp(sign * hardware.STAND_POSE['thigh'])
            knees[name] = clamp(sign * hardware.STAND_POSE['knee'])
        write_pose(thighs, knees)

    def parse_stride(value):
        lo, hi = STRIDE_RANGE
        if (isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not lo <= value <= hi):
            raise ValueError('Stride must be between %d and %d degrees.' % (lo, hi))
        return int(round(value))

    def walker(stop_event):
        start = time.monotonic()
        while not stop_event.is_set():
            phase = 2 * math.pi * ((time.monotonic() - start) % PERIOD_SECONDS) / PERIOD_SECONDS
            stride = walk['stride']
            thighs = {}
            knees = {}
            for name in legs:
                thigh, knee = leg_angles(name, phase, stride)
                thighs[name] = thigh
                knees[name] = knee
            try:
                with lock:
                    write_pose(thighs, knees)
            except Exception as error:
                print('walktest walker error:', error, file=sys.stderr, flush=True)
                return
            stop_event.wait(STEP_DT)

    @app.errorhandler(ValueError)
    def _invalid(error):
        return jsonify(error=str(error)), 400

    @app.get('/state')
    def _get_state():
        with lock:
            return jsonify(snapshot())

    @app.post('/stand')
    def _stand():
        if is_walking():
            raise ValueError('Walk test is running — stop it first.')
        with lock:
            hold_stand_pose()
            return jsonify(snapshot())

    @app.post('/walk/start')
    def _walk_start():
        data = request.get_json(silent=True) or {}
        if 'stride' in data:
            walk['stride'] = parse_stride(data['stride'])
        with lock:
            if not is_walking():
                walk['stop'] = Event()
                walk['thread'] = Thread(
                    target=walker, args=(walk['stop'],), daemon=True)
                walk['thread'].start()
        return jsonify(snapshot())

    @app.post('/walk/stop')
    def _walk_stop():
        thread = walk['thread']
        stop = walk['stop']
        if thread is not None and stop is not None:
            stop.set()
            thread.join(timeout=2)
        with lock:
            hold_stand_pose()
            return jsonify(snapshot())

    @app.post('/walk/stride')
    def _walk_stride():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or 'stride' not in data:
            raise ValueError('Expected a JSON object with a "stride" field.')
        walk['stride'] = parse_stride(data['stride'])
        with lock:
            return jsonify(snapshot())

    @app.post('/release')
    def _release():
        thread = walk['thread']
        stop = walk['stop']
        if thread is not None and stop is not None:
            stop.set()
            thread.join(timeout=2)
        with lock:
            for channels in legs.values():
                bus.release(channels['thigh'])
                bus.release(channels['knee'])
                positions[channels['thigh']] = None
                positions[channels['knee']] = None
            return jsonify(snapshot())

    @app.get('/health')
    def _health():
        return jsonify({'healthy': True, 'armed': True, 'mode': 'walktest'})

    @app.get('/')
    def _index():
        return Response(_PAGE, mimetype='text/html')

    # Start up already standing so the operator doesn't see floppy legs.
    with lock:
        hold_stand_pose()

    return app


def release_all(app):
    bus = app.config['WALK_BUS']
    legs = app.config['WALK_LEGS']
    lock = app.config['WALK_LOCK']
    walk = app.config['WALK_STATE']
    thread = walk['thread']
    stop = walk['stop']
    if thread is not None and stop is not None:
        stop.set()
        thread.join(timeout=2)
    with lock:
        for channels in legs.values():
            bus.release(channels['thigh'])
            bus.release(channels['knee'])


_PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BRICQ walktest</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{font:16px system-ui;background:#101827;color:#edf2fa;max-width:720px;margin:36px auto;padding:0 20px}p{color:#bac8da;line-height:1.5}section{background:#1c293c;border:1px solid #34455d;border-radius:16px;padding:24px;margin:20px 0}h2{margin-top:0}output{display:block;font-size:30px;font-weight:700;margin:18px 0}input[type=range]{width:100%;margin:18px 0;accent-color:#60a5fa}.ends{display:flex;justify-content:space-between;color:#bac8da}button{font:inherit;background:#2563eb;color:white;border:0;border-radius:9px;padding:12px 24px;margin-top:12px;margin-right:8px;cursor:pointer}button.danger{background:#b91c1c}:disabled{opacity:.5}#status{min-height:1.5em}.hint{font-size:14px}code{background:#0b1220;padding:2px 6px;border-radius:4px}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #34455d;font-size:14px}
</style>
<h1>Walk test</h1>
<p>Trot gait: diagonal pairs move together, so two feet are always on the ground. Legs oscillate around the baked stand pose. Start with a small stride.</p>
<p id="status" role="status">Connecting…</p>
<section>
<h2>Stride</h2>
<output id="stride-value" for="stride-slider">Step: 15°</output>
<input id="stride-slider" aria-label="Stride amplitude" type="range" min="5" max="25" step="1" value="15">
<div class="ends"><span>5°</span><span>small ↔ big</span><span>25°</span></div>
<button id="walk-btn" type="button" disabled>Start walking</button>
<button id="stand-btn" type="button">Hold stand pose</button>
<button id="release-btn" class="danger" type="button">Release (E-STOP)</button>
</section>
<section>
<h2>Legs</h2>
<table id="legs"><thead><tr><th>Leg</th><th>Phase</th><th>Thigh ch</th><th>Knee ch</th><th>Thigh°</th><th>Knee°</th></tr></thead><tbody></tbody></table>
</section>
<script>
const status=document.getElementById('status');
const strideSlider=document.getElementById('stride-slider');
const strideValue=document.getElementById('stride-value');
const walkBtn=document.getElementById('walk-btn');
const standBtn=document.getElementById('stand-btn');
const releaseBtn=document.getElementById('release-btn');
let walking=false;
let busy=false;
let pollId=null;
let strideSending=false;
function fmt(a){return a===null?'—':`${a>0?'+':''}${a}°`}
function show(data){
  walking=!!data.walking;
  walkBtn.textContent=walking?'Stop walking':'Start walking';
  walkBtn.disabled=false;
  if(typeof data.stride==='number'&&document.activeElement!==strideSlider&&!strideSending){
    strideSlider.value=data.stride;
    strideValue.textContent=`Step: ${data.stride}°`;
  }
  const tbody=document.querySelector('#legs tbody');
  tbody.innerHTML='';
  for(const leg of data.legs){
    const row=document.createElement('tr');
    row.innerHTML=`<td>${leg.leg}</td><td>${leg.offset_deg}°</td><td>${leg.thigh_channel}</td><td>${leg.knee_channel}</td><td>${fmt(leg.thigh_angle)}</td><td>${fmt(leg.knee_angle)}</td>`;
    tbody.appendChild(row);
  }
  if(walking&&pollId===null){
    pollId=setInterval(pollState,200);
  }else if(!walking&&pollId!==null){
    clearInterval(pollId);pollId=null;
  }
}
async function pollState(){
  try{
    const response=await fetch('/state',{cache:'no-store'});
    if(response.ok)show(await response.json());
  }catch(_){/* keep polling */}
}
function preview(){
  strideValue.textContent=`Step: ${strideSlider.value}°`;
}
async function post(path,payload,label){
  if(busy)return;
  busy=true;
  walkBtn.disabled=true;standBtn.disabled=true;releaseBtn.disabled=true;
  try{
    const response=await fetch(path,{
      method:'POST',
      headers:payload?{'Content-Type':'application/json'}:{},
      body:payload?JSON.stringify(payload):null
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.error||`${label} failed`);
    show(data);
    status.textContent=walking?'Walking…':'Holding stand pose.';
  }catch(error){
    status.textContent=`${label} failed: ${error.message}`;
  }finally{
    standBtn.disabled=false;releaseBtn.disabled=false;busy=false;
  }
}
async function sendStride(){
  const stride=Number(strideSlider.value);
  strideSending=true;
  try{
    const response=await fetch('/walk/stride',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({stride})
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'Stride update failed');
    show(data);
  }catch(error){
    status.textContent='Stride not applied. '+error.message;
  }finally{strideSending=false;}
}
strideSlider.addEventListener('input',preview);
strideSlider.addEventListener('change',sendStride);
walkBtn.addEventListener('click',()=>{
  if(walking){post('/walk/stop',null,'Stop');}
  else{post('/walk/start',{stride:Number(strideSlider.value)},'Start');}
});
standBtn.addEventListener('click',()=>post('/stand',null,'Stand'));
releaseBtn.addEventListener('click',()=>post('/release',null,'Release'));
(async()=>{
  try{
    const response=await fetch('/state',{cache:'no-store'});
    if(!response.ok)throw Error('Could not load state');
    show(await response.json());
    status.textContent=walking?'Walking…':'Standing. Press start to begin trot.';
  }catch(error){status.textContent=error.message;}
})();
</script>
</html>'''


def main():
    bus = hardware.default_bus()
    app = create_app(bus)

    def _cleanup(*_):
        release_all(app)
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    print('walktest running — reach it from your laptop at:', flush=True)
    print('  USB   http://10.12.194.1:5000', flush=True)
    print('  Wi-Fi http://bricq.local:5000', flush=True)
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    finally:
        release_all(app)


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print('walktest:', error, file=sys.stderr)
        sys.exit(1)
