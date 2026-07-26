# Third-Party Notices

The repository MIT License covers StructVision Cloud's original code and the
MAMT2 runtime implemented by the project author. It does not replace the
licenses of third-party software or assets.

## Detectron2

- Project: Detectron2
- Source: <https://github.com/facebookresearch/detectron2>
- License: Apache License 2.0

The repository contains `worker/detectron2-0.6-container.patch`. The Worker
build also downloads a pinned, project-built Detectron2 wheel from the
StructVision Cloud GitHub Release and installs it into the Worker image. The
wheel is not committed to this Git repository. Detectron2 remains subject to
its [upstream license](https://github.com/facebookresearch/detectron2/blob/main/LICENSE).

## Vite / create-vite template assets

- Project: Vite / create-vite
- Source: <https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react>
- License: MIT

The tracked files `frontend/src/assets/react.svg`,
`frontend/src/assets/vite.svg`, `frontend/public/favicon.svg`, and
`frontend/public/icons.svg` originate from the create-vite React template.
They remain subject to the
[Vite license](https://github.com/vitejs/vite/blob/main/LICENSE). Project
names, logos, and other trademarks remain the property of their respective
owners.

Python and npm dependencies installed from the repository's locked dependency
files remain subject to the licenses shipped by their respective projects and
packages.
