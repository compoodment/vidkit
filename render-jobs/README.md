# Render jobs

Render jobs are tiny handoff packets for a remote renderer/agent on a GPU workstation.

The repo branch carries the reusable renderer code. A job folder carries the specific scene, output name, quality settings, and exact command for one render request.

Recommended handoff loop:

1. The directing agent creates a branch, e.g. `render/glass-orbit-cathedral-rtx3060`.
2. The directing agent adds/updates `render-jobs/<job-id>/` with `scene.json`, `run.sh`, and `README.md`.
3. The remote renderer pulls that exact branch and runs the job script.
4. The remote renderer returns `outputs/<job-id>.mp4`, `ffprobe.json`, and any error log.
5. The directing agent verifies frames/contact sheet and assembles/polishes with Vidkit if needed.

This keeps the instructions deterministic: the remote renderer does not infer what to render; it checks out the named branch/job ID and runs the script in that job folder.
