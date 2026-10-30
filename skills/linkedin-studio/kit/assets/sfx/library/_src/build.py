import json,os,subprocess,numpy as np,soundfile as sf,pyloudnorm as pyln
from scipy.signal import resample_poly
SR=48000; OUT="/workspace/video-studio/assets/sfx/library"; os.makedirs(OUT,exist_ok=True)
K="CC0 1.0 (Kenney.nl)"; O="CC0 1.0 (OpenGameArt)"; C0="CC0 1.0 (Wikimedia Commons)"; PD="Public domain (Wikimedia Commons)"; S="CC0 1.0 (original, synthesized for Dazzbuilds)"
ku=lambda p:f"https://kenney.nl/assets/{p}"; ou=lambda p:f"https://opengameart.org/content/{p}"
cm=json.load(open("commons/meta.json"))
def cu(f): return cm[f]["page"]
KI="interface-sounds/Audio/"; KU="ui-audio/Audio/"; KD="digital-audio/Audio/"; KM="impact-sounds/Audio/"; KR="rpg-audio/Audio/"; KC="casino-audio/Audio/"; KS="sci-fi-sounds/Audio/"
MS="oga/MoreSounds/"
SRC=ku("interface-sounds"),ku("ui-audio"),ku("digital-audio"),ku("impact-sounds"),ku("rpg-audio"),ku("casino-audio"),ku("sci-fi-sounds")
kp={KI:SRC[0],KU:SRC[1],KD:SRC[2],KM:SRC[3],KR:SRC[4],KC:SRC[5],KS:SRC[6]}
def k(path): 
    for pre,u in kp.items():
        if path.startswith(pre): return u
# (category, descriptor, src path, source url, license, opts)
L=[
("mouse_click","mouse",KU+"mouseclick1.ogg",None,K,{}),
("mouse_click","soft",KU+"click1.ogg",None,K,{}),
("mouse_click","crisp",KU+"click3.ogg",None,K,{}),
("mouse_click","ui",KI+"click_002.ogg",None,K,{}),
("ui_tap","select",KI+"select_001.ogg",None,K,{}),
("ui_tap","toggle",KI+"toggle_001.ogg",None,K,{}),
("ui_tap","switch",KI+"switch_002.ogg",None,K,{}),
("ui_tap","plastic",KU+"switch5.ogg",None,K,{}),
("keyboard_typing","modelm_loop","commons/Typing_-_Model_M_1986.ogg","commons",C0,{"loop":(2.0,3.0)}),
("keyboard_typing","mech_loop","oga/unicae_games_keyboard_soundpack_1_0/Generated Typing/generated-004_medium.wav",ou("keyboard-soundpack-1-typing-and-single-keystrokes"),O,{"loop":(0.5,3.0)}),
("keyboard_typing","laptop_loop","oga/typing_0.ogg",ou("typing-soundeffect"),O,{"loop":(0.8,3.0)}),
("keyboard_typing","fast_loop","commons/Typing_fast.ogg","commons",PD,{"loop":(6.3,3.0)}),
("text_pop","bubble","oga/3pops/3pops/pop1.ogg",ou("3-pop-sounds"),O,{}),
("text_pop","bubble","oga/3pops/3pops/pop2.ogg",ou("3-pop-sounds"),O,{}),
("text_pop","pluck",KI+"pluck_001.ogg",None,K,{}),
("text_pop","blip","synth/text_pop_synth.wav","synth",S,{}),
("sticker_pop","spring","oga/100-CC0-SFX_0/spring_01.ogg",ou("100-cc0-sfx"),O,{}),
("sticker_pop","spring","oga/100-CC0-SFX_0/spring_03.ogg",ou("100-cc0-sfx"),O,{}),
("sticker_pop","boing","synth/sticker_boing_synth.wav","synth",S,{}),
("sticker_pop","pop","oga/3pops/3pops/pop3.ogg",ou("3-pop-sounds"),O,{}),
("whoosh_short","swosh","oga/qubodup-timehitwind/60009__qubodup__swosh_22.flac",ou("wind-hit-time-morph"),O,{}),
("whoosh_short","mega","oga/qubodup-timehitwind/qubodup-megaswosh1.wav",ou("wind-hit-time-morph"),O,{}),
("whoosh_short","swish","oga/swishes/swishes/swish-9.wav",ou("swishes-sound-pack"),O,{}),
("whoosh_short","swish","oga/swishes/swishes/swish-7.wav",ou("swishes-sound-pack"),O,{}),
("whoosh_long","slomo","oga/qubodup-timehitwind/qubodup-slomo1.wav",ou("wind-hit-time-morph"),O,{}),
("whoosh_long","mega","oga/qubodup-timehitwind/qubodup-megaswosh2.wav",ou("wind-hit-time-morph"),O,{}),
("whoosh_long","sweep","synth/whoosh_long_synth.wav","synth",S,{}),
("paper_tear","rip","oga/paper_ripped_-_1.mp3",ou("various-paper-sound-effects"),O,{}),
("paper_tear","tape_rip",MS+"Paper & Stationery/Stationery_06.wav",ou("202-more-sound-effects"),O,{"note":"picked by spectrum (broadband rip texture), likely masking-tape pull; confirm by ear"}),
("paper_tear","tape_rip",MS+"Paper & Stationery/Stationery_07.wav",ou("202-more-sound-effects"),O,{"note":"picked by spectrum (broadband rip texture), likely masking-tape pull; confirm by ear"}),
("paper_tear","crackle","synth/paper_tear_synth.wav","synth",S,{}),
("paper_slide","bookflip",KR+"bookFlip1.ogg",None,K,{}),
("paper_slide","bookflip",KR+"bookFlip2.ogg",None,K,{}),
("paper_slide","card_slide",KC+"card-slide-1.ogg",None,K,{}),
("paper_slide","page_turn","commons/Turning_a_page.ogg","commons",PD,{"seg":(1.1,2.65)}),
("camera_shutter","dslr","oga/MoreSounds/Camera/Camera_01.wav",ou("202-more-sound-effects"),O,{}),
("camera_shutter","dslr","oga/MoreSounds/Camera/Camera_02.wav",ou("202-more-sound-effects"),O,{}),
("camera_shutter","photo","oga/photo.ogg",ou("camera"),O,{}),
("camera_shutter","holga","commons/Holga_shuttersound.ogg","commons",PD,{}),
("notification_ding","confirm",KI+"confirmation_001.ogg",None,K,{}),
("notification_ding","confirm",KI+"confirmation_002.ogg",None,K,{}),
("notification_ding","bong",KI+"bong_001.ogg",None,K,{}),
("notification_ding","bell","oga/100-CC0-SFX_0/bell_01.ogg",ou("100-cc0-sfx"),O,{}),
("glitch","stutter","synth/glitch_stutter_a.wav","kenney_glitch",K+" - derived edit",{}),
("glitch","stutter","synth/glitch_stutter_b.wav","kenney_glitch",K+" - derived edit",{}),
("glitch","datanoise","synth/glitch_datanoise.wav","kenney_glitch",K+" - derived edit",{}),
("glitch","micro",KI+"glitch_002.ogg",None,K,{}),
("riser","noise_2s","synth/riser_noise2s.wav","synth",S,{"keep_tail":True}),
("riser","tonal_4s","synth/riser_tonal4s.wav","synth",S,{"keep_tail":True}),
("riser","phonk_4s","commons/Phonk_Riser__1__Sample.wav","commons",C0,{"seg":(4.5,8.6)}),
("impact","sub_boom","synth/impact_subboom.wav","synth",S,{}),
("impact","cine_hit","synth/impact_cinehit.wav","synth",S,{}),
("impact","punch",KM+"impactPunch_heavy_000.ogg",None,K,{}),
("impact","lowfreq_boom",KS+"lowFrequency_explosion_000.ogg",None,K,{}),
("cash_success","register","commons/Cash_register.ogg","commons",PD,{}),
("cash_success","coins",KR+"handleCoins.ogg",None,K,{}),
("cash_success","chime","oga/completetask_0.mp3",ou("completion-sound"),O,{}),
("cash_success","powerup",KD+"powerUp2.ogg",None,K,{}),
("error_buzz","error",KI+"error_001.ogg",None,K,{}),
("error_buzz","error",KI+"error_004.ogg",None,K,{}),
("error_buzz","error",KI+"error_006.ogg",None,K,{}),
("error_buzz","lowdown",KD+"lowDown.ogg",None,K,{}),
("scroll_tick","scroll",KI+"scroll_001.ogg",None,K,{}),
("scroll_tick","scroll",KI+"scroll_002.ogg",None,K,{}),
("scroll_tick","tick",KI+"tick_001.ogg",None,K,{}),
("scroll_tick","tick",KI+"tick_002.ogg",None,K,{}),
]
meter=pyln.Meter(SR)
def load(p,seg=None):
    cmd=["ffmpeg","-v","error"]+(["-ss",str(seg[0]),"-to",str(seg[1])] if seg else [])+["-i",p,"-ac","2","-ar",str(SR),"-f","f32le","-"]
    x=np.frombuffer(subprocess.run(cmd,capture_output=True,check=True).stdout,np.float32).reshape(-1,2).astype(np.float64)
    if np.allclose(x[:,0],x[:,1],atol=1e-4): x=x[:,:1]
    return x
def trim(x,rel=-45,absl=-62):
    m=np.abs(x).max(1); thr=max(m.max()*10**(rel/20),10**(absl/20)); idx=np.where(m>thr)[0]
    a=max(0,idx[0]-int(.002*SR)); b=min(len(x),idx[-1]+int(.02*SR)); y=x[a:b].copy()
    fi=min(int(.002*SR),len(y)//4); fo=min(int(.012*SR),len(y)//4)
    if a>0: y[:fi]*=np.linspace(0,1,fi)[:,None]
    y[-fo:]*=np.linspace(1,0,fo)[:,None]; return y
def loopcut(x,start,dur):
    m=np.convolve(np.abs(x).max(1),np.ones(240)/240,'same')
    def q(t,w=.12):
        c=int(t*SR); a=max(0,c-int(w*SR)); return a+int(np.argmin(m[a:c+int(w*SR)]))
    a=q(start); b=q(start+dur); y=x[a:b].copy(); f=int(.004*SR)
    y[:f]*=np.linspace(0,1,f)[:,None]; y[-f:]*=np.linspace(1,0,f)[:,None]; return y
def mom_max(y):
    w=int(.4*SR); h=int(.1*SR)
    if len(y)<w: y=np.vstack([y,np.zeros((w-len(y),y.shape[1]))])
    best=-120
    for s in range(0,len(y)-w+1,h):
        blk=y[s:s+w]
        try: v=meter.integrated_loudness(blk)
        except Exception: continue
        if np.isfinite(v): best=max(best,v)
    return best
def tpeak(y): return 20*np.log10(np.abs(resample_poly(y,4,1,axis=0)).max()+1e-12)
man=[]; cnt={}
for cat,desc,p,src,lic,o in L:
    x=load(p,o.get("seg"))
    y=loopcut(x,*o["loop"]) if "loop" in o else (x if o.get("keep_tail") else trim(x))
    lu=mom_max(y); pk=tpeak(y); g=-16-lu; limited=False
    if pk+g>-3: g=-3-pk; limited=True
    y=y*10**(g/20)
    cnt[cat]=cnt.get(cat,0)+1; fn=f"{cat}_{desc}_{cnt[cat]:02d}.wav"
    sf.write(os.path.join(OUT,fn),y.astype(np.float32),SR,subtype="PCM_24")
    if src=="commons": src=cu(os.path.basename(p))
    elif src=="kenney_glitch": src=ku("interface-sounds")+" + "+ku("sci-fi-sounds")+" (chopped/re-sequenced locally by _src/glitch.py)"
    elif src=="synth": src="synthesized locally (assets/sfx/library/_src/synth.py), no third-party audio"
    elif src is None: src=k(p)
    e=dict(file=fn,category=cat,duration=round(len(y)/SR,3),channels=y.shape[1],source_url=src,original_file=os.path.basename(p),license=lic,
           max_momentary_lufs=round(mom_max(y),1),true_peak_dbfs=round(tpeak(y),1),peak_limited=limited,loopable="loop" in o)
    if p.startswith("commons/"): e["author"]=cm[os.path.basename(p)]["artist"].strip()[:80]
    if "note" in o: e["note"]=o["note"]
    man.append(e); print(f"{fn:40s} {e['duration']:6.2f}s LUFSm={e['max_momentary_lufs']:6.1f} TP={e['true_peak_dbfs']:5.1f} {'(peak-limited)' if limited else ''}")
json.dump({"generated":"2026-10-20","format":"WAV 48 kHz 24-bit PCM","normalization":"gain to max momentary (400 ms) loudness -16 LUFS, capped so 4x-oversampled true peak <= -3 dBFS (transient-heavy clicks end up quieter than -16 LUFS, by design: no limiter/compression applied)","counts":cnt,"files":man},open(os.path.join(OUT,"manifest.json"),"w"),indent=1)
print(cnt)
