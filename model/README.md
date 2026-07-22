# StructVision model runtime contract

This directory contains metadata and the inference configuration only. Model
weights, Detectron2 wheels, datasets, annotations, images, outputs, and access
tokens must not be committed here.

The runtime expects `model_best_segm.pth` from the public Hugging Face repository
`DavidYz/structvision-spalling`. Before use, the file must match the SHA256 in
`manifest.yaml`. The manifest and Helm download URL pin the model to the same
immutable Hugging Face commit revision.

`config.yaml` is the container inference configuration migrated without semantic
changes from the external artifact directory. Dataset names retained in the
training snapshot are configuration strings only; the online runtime does not
register or load a dataset.

The Worker image downloads the Detectron2 wheel from the versioned GitHub Release
URL recorded in `manifest.yaml`. `worker/install_detectron2_wheel.py` rejects the
download unless its SHA256 is exactly
`eb7295b6cb477467cb03660ea024a11ab13e97fc12b157040b9234897f809ace`.
