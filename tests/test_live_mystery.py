import urllib.request
import json

payload = {
    'script': "The hallway was completely empty. Then Room 307's door slowly opened. Security rushed toward the room.",
    'voice_rate': '+10%'
}

req = urllib.request.Request(
    'http://localhost:8000/api/prepare_scenes',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print('SUCCESS! Response for Mystery Short:')
        print('Topic:', res.get('topic'))
        print('Duration:', res.get('est_duration'))
        print('Scenes count:', len(res.get('scenes', [])))
        for s in res.get('scenes', []):
            sid = s.get('scene_id')
            txt = s.get('text')
            src = s.get('source')
            score = s.get('validation_score')
            print(f'Scene {sid}: {txt}')
            print(f'  source: {src} | score: {score}')
            print('  must_show:', s.get('must_show'))
            print('  shot:', s.get('shot_type'), '| motion:', s.get('camera_motion'))
            print('  image_url:', s.get('image_url'))
except Exception as e:
    print('Failed:', e)
