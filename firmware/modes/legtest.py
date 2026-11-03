"""Leg testing mode: Flask UI driving one leg's servos directly.

Pick the leg at startup (`bricq legtest front-right`); the UI, routes, and
driver code are the same for every leg. Angles are commands (-90..+90), not
measured positions; the servo bus does the final mapping to pulse widths."""
import json
import math
import os
import signal
import sys
from threading import Lock

from flask import Flask, Response, jsonify, request

# Allow `python modes/legtest.py` to find firmware/hardware.py when
# invoked directly from the installed release.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hardware  # noqa: E402


def create_app(leg_name, bus):
    channels = hardware.resolve_leg(leg_name)
    panel = [
        {'channel': channel, 'name': joint.capitalize()}
        for joint, channel in channels.items()
    ]
    positions = {entry['channel']: None for entry in panel}
    lock = Lock()

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 2048
    app.config['LEGTEST_BUS'] = bus
    app.config['LEGTEST_LEG'] = leg_name
    app.config['LEGTEST_PANEL'] = panel
    app.config['LEGTEST_POSITIONS'] = positions
    app.config['LEGTEST_LOCK'] = lock

    def snapshot():
        return {
            'leg': leg_name,
            'servos': [
                {'channel': entry['channel'],
                 'name': entry['name'],
                 'angle': positions[entry['channel']]}
                for entry in panel
            ],
        }

    @app.errorhandler(ValueError)
    def _invalid(error):
        return jsonify(error=str(error)), 400

    @app.get('/state')
    def _get_state():
        with lock:
            return jsonify(snapshot())

    @app.post('/move')
    @app.post('/centre')
    def _move():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object.')
        channel = data.get('channel')
        if channel not in positions:
            raise ValueError('Unknown servo channel.')
        angle = 0 if request.path == '/centre' else data.get('angle')
        lo, hi = hardware.ANGLE_RANGE
        if (isinstance(angle, bool)
                or not isinstance(angle, (int, float))
                or not math.isfinite(angle)
                or not lo <= angle <= hi):
            raise ValueError('Angle must be between %d and +%d degrees.' % (lo, hi))
        with lock:
            bus.set_angle(channel, angle)
            positions[channel] = angle
            return jsonify(snapshot())

    @app.get('/health')
    def _health():
        return jsonify({
            'healthy': True,
            'armed': True,
            'mode': 'legtest',
            'leg': leg_name,
        })

    @app.get('/')
    def _index():
        return Response(_render(leg_name, panel), mimetype='text/html')

    return app


def release_all(app):
    bus = app.config['LEGTEST_BUS']
    positions = app.config['LEGTEST_POSITIONS']
    lock = app.config['LEGTEST_LOCK']
    with lock:
        for channel in positions:
            bus.release(channel)


def _render(leg_name, panel):
    channels_json = json.dumps([entry['channel'] for entry in panel])
    panel_json = json.dumps(panel)
    return _PAGE.replace('__LEG__', leg_name) \
                .replace('__CHANNELS__', channels_json) \
                .replace('__PANEL__', panel_json)


_PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BRICQ legtest · __LEG__</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{font:16px system-ui;background:#101827;color:#edf2fa;max-width:720px;margin:36px auto;padding:0 20px}p{color:#bac8da;line-height:1.5}section{background:#1c293c;border:1px solid #34455d;border-radius:16px;padding:24px;margin:20px 0}h2{margin-top:0}output{display:block;font-size:36px;font-weight:700;margin:18px 0}input[type=range]{width:100%;margin:18px 0;accent-color:#60a5fa}.ends{display:flex;justify-content:space-between;color:#bac8da}button{font:inherit;background:#2563eb;color:white;border:0;border-radius:9px;padding:12px 24px;margin-top:20px;cursor:pointer}:disabled{opacity:.5}#status{min-height:1.5em}
</style>
<h1>Leg test · __LEG__</h1>
<p>Direct servo angles. 0° is the servo centre. Sliders commit on release.</p>
<p id="status" role="status">Connecting…</p>
<main id="servos"></main>
<script>
const panel=__PANEL__;
const channels=__CHANNELS__;
const status=document.getElementById('status');
let busy=false;
function show(data){
  for(const servo of data.servos){
    const a=servo.angle;
    document.getElementById('slider'+servo.channel).value=a===null?0:a;
    document.getElementById('value'+servo.channel).textContent=a===null?'Released':`${a>0?'+':''}${a}°`;
  }
}
function preview(ch){
  const a=Number(document.getElementById('slider'+ch).value);
  document.getElementById('value'+ch).textContent=`${a>0?'+':''}${a}° (preview)`;
}
async function command(ch,centre=false){
  if(busy)return;
  busy=true;
  const controls=document.querySelectorAll('input,button');
  controls.forEach(el=>el.disabled=true);
  try{
    const angle=Number(document.getElementById('slider'+ch).value);
    const response=await fetch(centre?'/centre':'/move',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({channel:ch,angle})
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'Move failed');
    show(data);status.textContent='Ready.';
  }catch(error){
    status.textContent='Command not confirmed. '+error.message;
  }finally{controls.forEach(el=>el.disabled=false);busy=false;}
}
(async()=>{
  try{
    for(const entry of panel){
      const section=document.createElement('section');
      section.innerHTML=`<h2>${entry.name} · channel ${entry.channel}</h2>
        <output id="value${entry.channel}" for="slider${entry.channel}">Released</output>
        <input id="slider${entry.channel}" aria-label="${entry.name} servo angle" type="range" min="-90" max="90" step="1" value="0">
        <div class="ends"><span>−90°</span><span>0°</span><span>+90°</span></div>
        <button type="button">Centre</button>`;
      section.querySelector('input').addEventListener('input',()=>preview(entry.channel));
      section.querySelector('input').addEventListener('change',()=>command(entry.channel));
      section.querySelector('button').addEventListener('click',()=>command(entry.channel,true));
      document.getElementById('servos').appendChild(section);
    }
    const response=await fetch('/state',{cache:'no-store'});
    if(!response.ok)throw Error('Could not load servo state');
    show(await response.json());
    status.textContent='Ready. Servos move when you use a control.';
  }catch(error){status.textContent=error.message;}
})();
</script>
</html>'''


def main(leg_name):
    bus = hardware.default_bus()
    app = create_app(leg_name, bus)

    def _cleanup(*_):
        release_all(app)
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    print('legtest (%s) running — reach it from your laptop at:' % leg_name, flush=True)
    print('  USB   http://10.12.194.1:5000', flush=True)
    print('  Wi-Fi http://bricq.local:5000', flush=True)
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    finally:
        release_all(app)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: legtest <leg-name>', file=sys.stderr)
        sys.exit(2)
    try:
        main(sys.argv[1])
    except ValueError as error:
        print('legtest:', error, file=sys.stderr)
        sys.exit(1)
