#!/bin/sh
# Downloads Eddie's voice model (Kokoro v1.0). int8 is ~90 MB and plenty for speech; set FULL=1 for the 310 MB model.
set -e
DIR=${EDDIE_VOICE_DIR:-backend/voice_models}
mkdir -p "$DIR"
BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
if [ "$FULL" = "1" ]; then M=kokoro-v1.0.onnx; else M=kokoro-v1.0.int8.onnx; fi
[ -f "$DIR/$M" ] || curl -L -o "$DIR/$M" "$BASE/$M"
[ -f "$DIR/voices-v1.0.bin" ] || curl -L -o "$DIR/voices-v1.0.bin" "$BASE/voices-v1.0.bin"
echo "Eddie's voice model is in $DIR"
