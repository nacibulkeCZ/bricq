"""Stand pose tuning: find a stable whole-body crouch before coordinated motion.

Two sliders (thigh, knee) drive all four legs simultaneously. Left-side legs
receive a sign flip so the physically mirrored servos agree with the commanded
body angle. The intended workflow is: run `bricq stand`, drag the sliders until
the robot balances on all four feet, write down the numbers, and bake them into
a STAND_POSE constant that walk-style modes can oscillate around."""
import json
import math
import os
import signal
import sys
from threading import Lock

from flask import Flask, Response, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hardware  # noqa: E402


def create_app(bus):
    legs = {name: hardware.resolve_leg(name) for name in hardware.LEG_SIGNS}
    pose = dict(hardware.STAND_POSE)
    lock = Lock()

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 2048
    app.config['STAND_BUS'] = bus
    app.config['STAND_LEGS'] = legs
    app.config['STAND_POSE'] = pose
    app.config['STAND_LOCK'] = lock

    def snapshot():
        return {
            'pose': dict(pose),
            'legs': [
                {'leg': name,
                 'sign': hardware.LEG_SIGNS[name],
                 'thigh_channel': channels['thigh'],
                 'knee_channel': channels['knee']}
                for name, channels in legs.items()
            ],
        }

    def apply_pose():
        for name, channels in legs.items():
            sign = hardware.LEG_SIGNS[name]
            bus.set_angle(channels['thigh'], sign * pose['thigh'])
            bus.set_angle(channels['knee'], sign * pose['knee'])

    def parse_angle(key, value):
        lo, hi = hardware.ANGLE_RANGE
        if (isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not lo <= value <= hi):
            raise ValueError('%s angle must be between %d and +%d degrees.' % (key, lo, hi))
        return int(round(value))

    @app.errorhandler(ValueError)
    def _invalid(error):
        return jsonify(error=str(error)), 400

    @app.get('/state')
    def _get_state():
        with lock:
            return jsonify(snapshot())

    @app.post('/pose')
    def _set_pose():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object.')
        updates = {key: parse_angle(key, data[key])
                   for key in ('thigh', 'knee') if key in data}
        with lock:
            pose.update(updates)
            apply_pose()
            return jsonify(snapshot())

    @app.post('/release')
    def _release():
        with lock:
            for channels in legs.values():
                bus.release(channels['thigh'])
                bus.release(channels['knee'])
            return jsonify(snapshot())

    @app.get('/health')
    def _health():
        return jsonify({'healthy': True, 'armed': True, 'mode': 'stand'})

    @app.get('/')
    def _index():
        return Response(_PAGE, mimetype='text/html')

    return app


def release_all(app):
    bus = app.config['STAND_BUS']
    legs = app.config['STAND_LEGS']
    lock = app.config['STAND_LOCK']
    with lock:
        for channels in legs.values():
            bus.release(channels['thigh'])
            bus.release(channels['knee'])


_PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BRICQ stand pose</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{font:16px system-ui;background:#101827;color:#edf2fa;max-width:720px;margin:36px auto;padding:0 20px}p{color:#bac8da;line-height:1.5}section{background:#1c293c;border:1px solid #34455d;border-radius:16px;padding:24px;margin:20px 0}h2{margin-top:0}output{display:block;font-size:36px;font-weight:700;margin:18px 0}input[type=range]{width:100%;margin:18px 0;accent-color:#60a5fa}.ends{display:flex;justify-content:space-between;color:#bac8da}button{font:inherit;background:#2563eb;color:white;border:0;border-radius:9px;padding:12px 24px;margin-top:20px;cursor:pointer}button.danger{background:#b91c1c}:disabled{opacity:.5}#status{min-height:1.5em}.hint{font-size:14px}code{background:#0b1220;padding:2px 6px;border-radius:4px}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #34455d;font-size:14px}
</style>
<h1>Stand pose</h1>
<p>Drag sliders to find a stable crouch. Both angles apply to all four legs at once; left-side legs are automatically sign-flipped. Write the final numbers down — they'll be baked into <code>hardware.STAND_POSE</code> for the walk test.</p>
<p id="status" role="status">Connecting…</p>
<section>
<h2>Thigh</h2>
<output id="thigh-value" for="thigh-slider">0°</output>
<input id="thigh-slider" aria-label="Thigh angle" type="range" min="-90" max="90" step="1" value="0">
<div class="ends"><span>−90°</span><span>0°</span><span>+90°</span></div>
<p class="hint">Positive swings the leg forward. Stand pose usually wants this near 0.</p>
</section>
<section>
<h2>Knee</h2>
<output id="knee-value" for="knee-slider">0°</output>
<input id="knee-slider" aria-label="Knee angle" type="range" min="-90" max="90" step="1" value="0">
<div class="ends"><span>−90°</span><span>0°</span><span>+90°</span></div>
<p class="hint">Negative bends the knee forward (tuck). Stand pose wants this negative to lower the body.</p>
</section>
<section>
<h2>Servos</h2>
<table id="legs"><thead><tr><th>Leg</th><th>Sign</th><th>Thigh ch</th><th>Knee ch</th></tr></thead><tbody></tbody></table>
<button id="release-btn" class="danger" type="button">Release all servos</button>
</section>
<script>
const status=document.getElementById('status');
const thighSlider=document.getElementById('thigh-slider');
const kneeSlider=document.getElementById('knee-slider');
const thighValue=document.getElementById('thigh-value');
const kneeValue=document.getElementById('knee-value');
const releaseBtn=document.getElementById('release-btn');
let busy=false;
function fmt(a){return `${a>0?'+':''}${a}°`}
function show(data){
  if(document.activeElement!==thighSlider){
    thighSlider.value=data.pose.thigh;
  }
  if(document.activeElement!==kneeSlider){
    kneeSlider.value=data.pose.knee;
  }
  thighValue.textContent=fmt(data.pose.thigh);
  kneeValue.textContent=fmt(data.pose.knee);
  const tbody=document.querySelector('#legs tbody');
  tbody.innerHTML='';
  for(const leg of data.legs){
    const row=document.createElement('tr');
    row.innerHTML=`<td>${leg.leg}</td><td>${leg.sign>0?'+1':'−1'}</td><td>${leg.thigh_channel}</td><td>${leg.knee_channel}</td>`;
    tbody.appendChild(row);
  }
}
function preview(){
  thighValue.textContent=`${fmt(Number(thighSlider.value))} (preview)`;
  kneeValue.textContent=`${fmt(Number(kneeSlider.value))} (preview)`;
}
async function send(payload,label){
  if(busy)return;
  busy=true;
  thighSlider.disabled=true;kneeSlider.disabled=true;releaseBtn.disabled=true;
  try{
    const response=await fetch('/pose',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'Pose rejected');
    show(data);
    status.textContent=`Pose applied — thigh ${fmt(data.pose.thigh)}, knee ${fmt(data.pose.knee)}.`;
  }catch(error){
    status.textContent=`${label} failed: ${error.message}`;
  }finally{
    thighSlider.disabled=false;kneeSlider.disabled=false;releaseBtn.disabled=false;busy=false;
  }
}
thighSlider.addEventListener('input',preview);
kneeSlider.addEventListener('input',preview);
thighSlider.addEventListener('change',()=>send({thigh:Number(thighSlider.value)},'Thigh'));
kneeSlider.addEventListener('change',()=>send({knee:Number(kneeSlider.value)},'Knee'));
releaseBtn.addEventListener('click',async()=>{
  if(busy)return;
  busy=true;releaseBtn.disabled=true;
  try{
    const response=await fetch('/release',{method:'POST'});
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'Release failed');
    show(data);
    status.textContent='All servos released. Robot has no holding torque.';
  }catch(error){
    status.textContent=`Release failed: ${error.message}`;
  }finally{releaseBtn.disabled=false;busy=false;}
});
(async()=>{
  try{
    const response=await fetch('/state',{cache:'no-store'});
    if(!response.ok)throw Error('Could not load state');
    show(await response.json());
    status.textContent='Ready. Move a slider to commit the pose.';
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

    print('stand running — reach it from your laptop at:', flush=True)
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
        print('stand:', error, file=sys.stderr)
        sys.exit(1)
