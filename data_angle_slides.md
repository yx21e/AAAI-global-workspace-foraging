# Data Angle Slides

## Slide 1 — Data-First Framing

**Title:** From 2D Demo to Data Contract

**Main message:** Since the 2D environment is handled by another part of the team, our data task is not to collect a generic external dataset. Our job is to define and collect the traces that make dissociation measurable.

**Slide bullets:**

- Unit of data = one timestamp in the global-workspace loop.
- Each timestamp should record:
  - environment state / stimulus
  - module proposals
  - importance scores
  - workspace winner
  - broadcast content
  - action, feedback, report, confidence
  - intervention / ablation label
- This gives us both task performance and consciousness-related functional markers.

**Speaker note:** The key move is to treat the system itself as the data generator. External datasets are useful later, but the core dataset is the fully logged internal trajectory.

---

## Slide 2 — What Data Is Used Where

**Title:** Data Needed by Experimental Stage

| Data type | What it contains | Used in which stage | What it measures |
|---|---|---|---|
| Main trajectory logs | state, action, reward, feedback | baseline runs | task success, obstacle avoidance, collect-return |
| Module competition logs | module output, score, winner, broadcast | every workspace step | bottleneck, winner dynamics, broadcast effects |
| Report + confidence logs | verbal report, confidence, ground truth | report/query steps | blindsight-like Type-1 vs Type-2 dissociation |
| Intervention labels | mask, delay, mismatch, lesion config | ablation/intervention runs | causal dependence of each dissociation marker |
| Explanation labels | true cause, generated explanation, consistency | post-hoc explanation steps | split-brain/confabulation-like mismatch |
| Optional multimodal clips | audio, video, transcript, alignment | later extension | McGurk/cross-modal integration |

**Speaker note:** The first four rows are essential. External multimodal data is not first-wave; it is for extensions after the system can already produce logged trajectories.

---

## Slide 3 — Candidate Sources and Download Readiness

**Title:** Candidate Data Sources: Ready vs Optional

| Source | Download ready / free? | How we would use it | Priority |
|---|---|---|---|
| Our generated workspace logs | Yes, created by us | main experimental dataset | A |
| Minari MiniGrid/BabyAI trajectories | Yes, public CLI datasets | offline baseline / trajectory format | A |
| MiniGrid / BabyAI | Code ready, not a fixed dataset | environment/data schema reference | A |
| GRID audiovisual corpus | Yes, Zenodo, CC-BY 4.0, large download | clean audio-video-transcript alignment | B |
| AVSpeech | CSV annotations ready, CC-BY 4.0; videos depend on YouTube availability | noisy real-world audiovisual extension | B |
| LRW | Academic non-commercial; requires BBC data sharing agreement; 70GB | lip-reading/cross-modal extension | C |
| LRS3-TED | Research dataset; access less immediate than GRID/AVSpeech | large-scale audiovisual extension | C |
| SoundSpaces | Public platform; scene assets have extra terms | future 3D audiovisual embodiment | C |

**Speaker note:** For the meeting, the main recommendation is: do not wait for external data. First define the timestamp log schema. Then use Minari/GRID/AVSpeech only where they add a specific evaluation or comparison.

---

# GPT Image Generation Prompts

## Prompt 1 — Slide 1 visual

Create a clean academic conference slide illustration showing a "data contract" for a multi-agent global workspace system. Use a 2D grid-world scene on the left with a small agent, base, resource zone, and obstacles. In the center, show several labeled modules: perception, motor, emotion, language. On the right, show a central workspace/controller selecting one winning message and broadcasting it back to all modules. Add small data-log cards below the loop labeled: state, proposals, scores, winner, broadcast, action, feedback, report, confidence, intervention. Style: modern research presentation, minimal, white background, subtle blue and green accents, no cartoonish characters, no decorative gradients, 16:9 aspect ratio, high readability.

## Prompt 2 — Slide 2 visual

Create a concise research slide diagram titled "Data Used by Experimental Stage". Show a left-to-right pipeline with four stages: baseline run, workspace competition, report/query, ablation/intervention. Under each stage, show small data fields: trajectory logs, module outputs, confidence reports, intervention labels. Above the pipeline, add three markers: task success, Type-1/Type-2 dissociation, confabulation mismatch. Style: clean systems diagram, academic, white background, flat icons, thin lines, restrained colors, 16:9 aspect ratio, no dense text.

## Prompt 3 — Slide 3 visual

Create a clean matrix-style slide visual comparing data sources by readiness. Rows: Our logs, Minari, MiniGrid/BabyAI, GRID, AVSpeech, LRW/LRS3, SoundSpaces. Columns: Main use, readiness, priority. Use check marks for ready sources, clock icons for approval/large-download sources, and small database icons. Style: professional academic slide, white background, subtle gray table lines, green for ready, amber for conditional, 16:9 aspect ratio, readable and not crowded.

