"""Local/Colab/Kaggle launcher for the VoxCPM2 engine (spec §8b). On Colab/Kaggle,
pair this with a tunnel (e.g. `cloudflared tunnel --url http://localhost:8800`) and
paste the printed URL into the studio's Settings -> Providers -> VoxCPM2 field."""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("VOXCPM_PORT", "8800"))
    uvicorn.run("engine:app", host="0.0.0.0", port=port)
