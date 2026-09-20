import sys
sys.path.insert(0, ".")
from engine.visual_director.planner import plan_visual_storyboard
from engine.visual_director.generator import CURATED_SCENE_ASSETS
from engine.smart_visuals import search_targeted_scene_image

script = "On March 8, 2014, Malaysia Airlines Flight MH370 took off from Kuala Lumpur to Beijing with 239 people on board. But less than an hour into the flight, something terrifying happened: the plane transponder suddenly went dark. Military radar detected the aircraft turning sharply off course, heading out over the vast, empty southern Indian Ocean. For years, the most expensive search in aviation history scanned hundreds of thousands of square miles of ocean floor, yet not a single trace was found in the abyss. What really happened to Flight 370 remains the greatest mystery of modern aviation."

plan = plan_visual_storyboard(script, 50.0)
print(f"Total scenes: {len(plan['scenes'])}")
for idx, sc in enumerate(plan['scenes']):
    txt = sc['narration']
    p = sc['image_prompt']
    sq = sc['search_query']
    check_text = f"{txt} {p} {sq}".lower()
    
    curated_match = None
    for kws, url in CURATED_SCENE_ASSETS:
        if any(k in check_text for k in kws):
            curated_match = kws[0]
            break
            
    print(f"\n[Scene {idx+1}] \"{txt[:45]}...\"")
    print(f"  Prompt: {p[:65]}...")
    print(f"  Search Query: {sq}")
    print(f"  Curated Match: {curated_match}")
    
    # Check what Wikimedia Commons returns for this search query
    auth = search_targeted_scene_image(sq, set())
    if auth:
        print(f"  COMMONS RETURNED: {auth.get('title')} -> {auth.get('url')[:60]}...")
