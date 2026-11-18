"""Mechanical zero calibration: one trim slider per servo.

When you screw a servo into the leg, the horn lands at an arbitrary rotation.
"0° in code" then means a different physical joint position for every servo.
This mode lets you adjust a per-channel trim offset live until a commanded 0°
puts every leg in the same canonical position. Copy the final dict into
hardware.SERVO_TRIMS."""
import json
import math
import os
import signal
import sys
from threading import Lock

from flask import Flask, Response, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hardware  # noqa: E402


TRIM_RANGE = (-45, 45)


def create_app(bus):
    legs = {name: hardware.resolve_leg(name) for name in hardware.LEG_SIGNS}
    # Panel of every wired servo with its leg/joint label.
    panel = []
    for leg_name, channels in legs.items():
        for joint in ('thigh', 'knee'):
            panel.append({'channel': channels[joint],
                          'leg': leg_name,
                          'joint': joint})
    panel.sort(key=lambda entry: entry['channel'])

    # Working copy of trims — gets mutated during the session, then baked.
    trims = {entry['channel']: hardware.SERVO_TRIMS.get(entry['channel'], 0)
             for entry in panel}
    # Last commanded raw angle (before trim) per channel, or None when released.
    commanded = {entry['channel']: None for entry in panel}
    lock = Lock()

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 2048
    app.config['CALIBRATE_BUS'] = bus
    app.config['CALIBRATE_PANEL'] = panel
    app.config['CALIBRATE_TRIMS'] = trims
    app.config['CALIBRATE_COMMANDED'] = commanded
    app.config['CALIBRATE_LOCK'] = lock

    def apply_trim_live(channel):
        # Push the new trim to the servo immediately so the user sees motion
        # as they drag the slider — but only if the servo is currently engaged.
        angle = commanded[channel]
        if angle is not None:
            bus.set_angle(channel, angle)

    def snapshot():
        return {
            'trim_range': list(TRIM_RANGE),
            'servos': [{
                'channel': entry['channel'],
                'leg': entry['leg'],
                'joint': entry['joint'],
                'trim': trims[entry['channel']],
                'commanded': commanded[entry['channel']],
            } for entry in panel],
            'trim_dict_literal': _format_trim_dict(trims),
        }

    def parse_trim(value):
        lo, hi = TRIM_RANGE
        if (isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not lo <= value <= hi):
            raise ValueError('Trim must be between %d and %d degrees.' % (lo, hi))
        return int(round(value))

    @app.errorhandler(ValueError)
    def _invalid(error):
        return jsonify(error=str(error)), 400

    @app.get('/state')
    def _get_state():
        with lock:
            return jsonify(snapshot())

    @app.post('/trim')
    def _set_trim():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object.')
        channel = data.get('channel')
        if channel not in trims:
            raise ValueError('Unknown servo channel.')
        trim = parse_trim(data.get('trim'))
        with lock:
            trims[channel] = trim
            hardware.SERVO_TRIMS[channel] = trim
            apply_trim_live(channel)
            return jsonify(snapshot())

    @app.post('/zero-all')
    def _zero_all():
        with lock:
            for channel in trims:
                bus.set_angle(channel, 0)
                commanded[channel] = 0
            return jsonify(snapshot())

    @app.post('/release')
    def _release():
        with lock:
            for channel in trims:
                bus.release(channel)
                commanded[channel] = None
            return jsonify(snapshot())

    @app.get('/health')
    def _health():
        return jsonify({'healthy': True, 'armed': True, 'mode': 'calibrate'})

    @app.get('/')
    def _index():
        return Response(_render(panel), mimetype='text/html')

    return app


def release_all(app):
    bus = app.config['CALIBRATE_BUS']
    trims = app.config['CALIBRATE_TRIMS']
    lock = app.config['CALIBRATE_LOCK']
    with lock:
        for channel in trims:
            bus.release(channel)


def _format_trim_dict(trims):
    """Pretty-print the trim dict for copy-paste into hardware.py."""
    items = ', '.join('%d: %d' % (ch, trim)
                      for ch, trim in sorted(trims.items()))
    return 'SERVO_TRIMS = {' + items + '}'


def _render(panel):
    return _PAGE.replace('__PANEL__', json.dumps(panel))


_PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BRICQ calibrate</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{font:16px system-ui;background:#101827;color:#edf2fa;max-width:720px;margin:36px auto;padding:0 20px}p{color:#bac8da;line-height:1.5}section{background:#1c293c;border:1px solid #34455d;border-radius:16px;padding:20px;margin:16px 0}h2{margin-top:0}output{display:block;font-size:22px;font-weight:700;margin:10px 0}input[type=range]{width:100%;margin:12px 0;accent-color:#60a5fa}.ends{display:flex;justify-content:space-between;color:#bac8da;font-size:13px}button{font:inherit;background:#2563eb;color:white;border:0;border-radius:9px;padding:12px 20px;margin-top:12px;margin-right:8px;cursor:pointer}button.danger{background:#b91c1c}:disabled{opacity:.5}#status{min-height:1.5em}pre{background:#0b1220;padding:12px;border-radius:8px;overflow-x:auto;font-size:13px;user-select:all}.hint{font-size:14px}
</style>
<h1>Servo trim calibration</h1>
<p>Click <b>Zero all</b>, then nudge each trim until the leg is in its canonical position (all four legs pointing the same way). When happy, copy the dict at the bottom into <code>hardware.SERVO_TRIMS</code>.</p>
<p id="status" role="status">Connecting…</p>
<section>
<button id="zero-btn" type="button">Zero all servos</button>
<button id="release-btn" class="danger" type="button">Release (E-STOP)</button>
</section>
<main id="servos"></main>
<section>
<h2>Current trim dict</h2>
<pre id="dict-output">SERVO_TRIMS = {...}</pre>
<p class="hint">Triple-click the block to select it, then paste into <code>firmware/hardware.py</code>.</p>
</section>
<script>
const panel=__PANEL__;
const status=document.getElementById('status');
const dictOutput=document.getElementById('dict-output');
const zeroBtn=document.getElementById('zero-btn');
const releaseBtn=document.getElementById('release-btn');
let busy=false;
function fmt(a){return a===null?'—':`${a>0?'+':''}${a}°`}
function show(data){
  dictOutput.textContent=data.trim_dict_literal;
  for(const servo of data.servos){
    const slider=document.getElementById('slider'+servo.channel);
    const value=document.getElementById('value'+servo.channel);
    const cmd=document.getElementById('cmd'+servo.channel);
    if(document.activeElement!==slider){
      slider.value=servo.trim;
    }
    value.textContent=`Trim: ${fmt(servo.trim)}`;
    cmd.textContent=`Commanded: ${fmt(servo.commanded)}`;
  }
}
async function setTrim(channel){
  if(busy)return;
  busy=true;
  try{
    const trim=Number(document.getElementById('slider'+channel).value);
    const response=await fetch('/trim',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({channel,trim})
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'Trim failed');
    show(data);
    status.textContent=`Trim ch${channel} = ${fmt(trim)}.`;
  }catch(error){
    status.textContent=`Trim failed: ${error.message}`;
  }finally{busy=false;}
}
async function post(path,label){
  if(busy)return;
  busy=true;
  zeroBtn.disabled=true;releaseBtn.disabled=true;
  try{
    const response=await fetch(path,{method:'POST'});
    const data=await response.json();
    if(!response.ok)throw Error(data.error||`${label} failed`);
    show(data);
    status.textContent=`${label} done.`;
  }catch(error){
    status.textContent=`${label} failed: ${error.message}`;
  }finally{zeroBtn.disabled=false;releaseBtn.disabled=false;busy=false;}
}
zeroBtn.addEventListener('click',()=>post('/zero-all','Zero all'));
releaseBtn.addEventListener('click',()=>post('/release','Release'));
(async()=>{
  try{
    for(const entry of panel){
      const section=document.createElement('section');
      section.innerHTML=`<h2>${entry.leg} · ${entry.joint} · ch${entry.channel}</h2>
        <output id="value${entry.channel}" for="slider${entry.channel}">Trim: 0°</output>
        <input id="slider${entry.channel}" aria-label="${entry.leg} ${entry.joint} trim" type="range" min="-45" max="45" step="1" value="0">
        <div class="ends"><span>−45°</span><span>0°</span><span>+45°</span></div>
        <p class="hint" id="cmd${entry.channel}">Commanded: —</p>`;
      section.querySelector('input').addEventListener('change',()=>setTrim(entry.channel));
      document.getElementById('servos').appendChild(section);
    }
    const response=await fetch('/state',{cache:'no-store'});
    if(!response.ok)throw Error('Could not load state');
    show(await response.json());
    status.textContent='Ready. Click "Zero all servos" to engage.';
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

    print('calibrate running — reach it from your laptop at:', flush=True)
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
        print('calibrate:', error, file=sys.stderr)
        sys.exit(1)
