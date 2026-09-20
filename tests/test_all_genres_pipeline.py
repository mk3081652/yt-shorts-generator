import os
import sys
sys.path.insert(0, ".")

from engine.visual_director.planner import plan_visual_storyboard
from engine.visual_director.generator import single_visual_attempt

scripts = {
    "Ancient Rome": "In 70 AD, the Roman Colosseum was built. Thousands of spectators gathered to watch gladiators battle for their lives. Outside, Roman legions marched through the marble streets of the eternal city.",
    "Bitcoin & Crypto": "In 2008, Satoshi Nakamoto published the Bitcoin whitepaper. Miners began validating transactions on the blockchain. Today, millions of gold and digital coins circulate in the global financial market.",
    "Wildlife": "In the African savannah, a pride of lions rests under an acacia tree. Suddenly, a lion stalks its prey through the golden grass. The great predator sprints across the dusty plains.",
    "Cyberpunk": "In the year 2085, neon rain falls across the skyscrapers of New Tokyo. Flying vehicles navigate between massive holographic advertisements. An elite hacker in a dark trench coat plugs into the cyber grid.",
    "Mystery Noir": "The detective walked into the dimly lit room. On the desk lay an old silver revolver and a locked leather journal. Outside, heavy fog rolled through the cobblestone alleyways.",
    "Aviation Mystery": "On March 8, 2014, Flight MH370 took off into the night sky with 239 passengers. Less than an hour later, the plane transponder went dark. A deep-sea submarine scanned the abyss of the ocean floor, but the mystery remains."
}

os.makedirs("outputs/test_genres", exist_ok=True)

print("=================================================================")
print("RUNNING END-TO-END VISUAL DIRECTOR PIPELINE ACROSS 6 DIVERSE GENRES")
print("=================================================================\n")

total_scenes = 0
passed_scenes = 0

for genre, script in scripts.items():
    print(f"\n>>> TESTING GENRE: {genre}")
    plan = plan_visual_storyboard(script, 15.0)
    scenes = plan.get("scenes", [])
    print(f"    Planned {len(scenes)} visual beats:")
    
    used_urls = set()
    for idx, sc in enumerate(scenes):
        total_scenes += 1
        scene_id = sc.get("scene_id")
        txt = sc.get("narration")
        sq = sc.get("search_query")
        prompt = sc.get("image_prompt")
        
        out_img = f"outputs/test_genres/{genre.lower().replace(' ', '_')}_{idx}.jpg"
        ok = single_visual_attempt(
            prompt=prompt,
            search_query=sq,
            output_path=out_img,
            scene_text=txt,
            used_urls=used_urls
        )
        
        file_size = os.path.getsize(out_img) if (ok and os.path.exists(out_img)) else 0
        if ok and file_size > 5000:
            passed_scenes += 1
            status = f"PASS ({file_size // 1024} KB)"
        else:
            status = "FAIL"
            
        print(f"    [{scene_id}] \"{txt[:40]}...\"")
        print(f"        Query: '{sq}' | Status: {status}")

print(f"\n=================================================================")
print(f"FINAL RESULT: {passed_scenes}/{total_scenes} scenes successfully matched and downloaded!")
print("=================================================================")
