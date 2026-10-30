# Dazzbuilds SFX library: licenses

Every file in this folder is free for commercial use with **no attribution requirement** (CC0 1.0 or public domain).
Nothing here is from Mixkit, Pixabay, Freesound, Sonniss, or any attribution-only / non-commercial source.
Per-file source URL, original filename, license and (for Wikimedia) author are in `manifest.json`.

## Sources

| Source | License | Packs / pages used |
|---|---|---|
| Kenney.nl (Kenney Vleugels) | CC0 1.0 | [Interface Sounds](https://kenney.nl/assets/interface-sounds), [UI Audio](https://kenney.nl/assets/ui-audio), [Impact Sounds](https://kenney.nl/assets/impact-sounds), [Digital Audio](https://kenney.nl/assets/digital-audio), [RPG Audio](https://kenney.nl/assets/rpg-audio), [Casino Audio](https://kenney.nl/assets/casino-audio), [Sci-fi Sounds](https://kenney.nl/assets/sci-fi-sounds). The original License.txt files are in `_src/licenses/`. |
| OpenGameArt.org (CC0-tagged entries only; license checked on each page) | CC0 1.0 | [100 CC0 SFX](https://opengameart.org/content/100-cc0-sfx), [202 More Sound Effects](https://opengameart.org/content/202-more-sound-effects), [Various paper sound effects](https://opengameart.org/content/various-paper-sound-effects), [3 Pop Sounds](https://opengameart.org/content/3-pop-sounds), [Swishes sound pack](https://opengameart.org/content/swishes-sound-pack), [Wind, hit, time morph (qubodup)](https://opengameart.org/content/wind-hit-time-morph), [Keyboard soundpack 1](https://opengameart.org/content/keyboard-soundpack-1-typing-and-single-keystrokes), [Typing soundeffect](https://opengameart.org/content/typing-soundeffect), [Camera](https://opengameart.org/content/camera), [Completion sound](https://opengameart.org/content/completion-sound) |
| Wikimedia Commons (only files whose license field is CC0 or Public domain) | CC0 1.0 / Public domain | Typing - Model M 1986 (Raymangold22, CC0), Typing fast (stephan, PD), Turning a page (planish, PD), Holga shuttersound (PD), Cash register (PD), Phonk Riser (1) Sample (CC0). Page links are in manifest.json. |
| Synthesized locally | CC0 1.0 (original, Dazzbuilds) | riser_noise_2s, riser_tonal_4s, impact_sub_boom, impact_cine_hit, whoosh_long_sweep, paper_tear_crackle, sticker_pop_boing, text_pop_blip, made with numpy in `_src/synth.py`. No third-party audio. |
| Derived edits of Kenney CC0 | CC0 1.0 | glitch_stutter_01/02, glitch_datanoise_03: Kenney glitch_00x + computerNoise re-sequenced/gated/bit-crushed by `_src/glitch.py`. |

Kenney asks (not requires) credit: "Kenney.nl". Optional credit line for descriptions: *SFX: Kenney.nl, OpenGameArt contributors, Wikimedia Commons (CC0/PD).*

## Processing
Silence trimmed (except risers and the typing loops, which are cut at quiet points between keystrokes with 4 ms fades), resampled to 48 kHz, WAV 24-bit.
Gain set so the loudest 400 ms window is -16 LUFS, then capped so the 4x-oversampled true peak is no more than -3 dBFS. Short transient sounds (clicks, ticks, micro-glitches) hit the peak cap first, so they measure quieter than -16 LUFS (`peak_limited: true` in the manifest). No limiter or compression was applied.
