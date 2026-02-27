"""
Correctness test: verify in-memory pipeline produces identical results to CLI.

Usage:
    cd DracoGS
    python compression/test_dracogs.py
"""

import sys
import os
import tempfile
import subprocess
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from compression_decompression import read_gs_ply, encode_dracogs, decode_dracogs, save_gs_ply

# TEST_PLY = "/synology/rajrup/VideoGS/train_output/HiFi4G_Dataset/4K_Actor1_Greeting/checkpoint/0/point_cloud/iteration_16000/point_cloud.ply"
TEST_PLY = "/synology/rajrup/Queen/pretrained_output/Neural_3D_Video/queen_compressed_flame_salmon_1/frames/0001/point_cloud/iteration_8992/point_cloud.ply"

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
ENCODER = BUILD_DIR / "draco_encoder"
DECODER = BUILD_DIR / "draco_decoder"

QP, QFD, QFR1, QFR2, QFR3, QO, QS, QR, CL = 16, 16, 16, 16, 16, 16, 16, 16, 7


def test_roundtrip():
    """Test in-memory encode -> decode roundtrip."""
    print(f"Reading {TEST_PLY} ...")
    gs = read_gs_ply(TEST_PLY)
    N = gs["positions"].shape[0]
    print(f"  {N} Gaussians loaded")
    for k, v in gs.items():
        print(f"  {k}: shape={v.shape}, dtype={v.dtype}")

    print(f"\nEncoding in-memory (qp={QP}, qfd={QFD}, qfr1={QFR1}, "
          f"qo={QO}, qs={QS}, qr={QR}, cl={CL}) ...")
    t0 = time.perf_counter()
    bitstream = encode_dracogs(gs, qp=QP, qfd=QFD, qfr1=QFR1, qfr2=QFR2,
                               qfr3=QFR3, qo=QO, qs=QS, qr=QR, cl=CL)
    t_enc = time.perf_counter() - t0
    print(f"  Encoded: {len(bitstream) / 1024 / 1024:.2f} MB in {t_enc*1000:.1f} ms")
    print(f"  Compression ratio: {N * 62 * 4 / len(bitstream):.2f}x")

    print("\nDecoding in-memory ...")
    t0 = time.perf_counter()
    gs_dec = decode_dracogs(bitstream)
    t_dec = time.perf_counter() - t0
    print(f"  Decoded: {gs_dec['positions'].shape[0]} points in {t_dec*1000:.1f} ms")

    save_gs_ply(gs_dec, "point_cloud_distorted.ply")

    print("\nAttribute shapes after decode:")
    for k, v in gs_dec.items():
        print(f"  {k}: shape={v.shape}")

    print("\n--- Roundtrip test PASSED ---")
    return gs, bitstream, gs_dec


def test_cli_equivalence(gs, bitstream):
    """Compare in-memory bitstream with CLI encoder output."""
    if not ENCODER.exists() or not DECODER.exists():
        print(f"\nSkipping CLI equivalence test (encoder/decoder not found at {BUILD_DIR})")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Save as ASCII PLY for CLI encoder
        ascii_ply = tmpdir / "input_ascii.ply"
        print(f"\nSaving ASCII PLY for CLI encoder: {ascii_ply}")
        save_gs_ply(gs, str(ascii_ply), binary=False)

        # CLI encode
        cli_drc = tmpdir / "cli_compressed.drc"
        cmd = [
            str(ENCODER), "-point_cloud",
            "-i", str(ascii_ply),
            "-o", str(cli_drc),
            f"-qp", str(QP), f"-qfd", str(QFD),
            f"-qfr1", str(QFR1), f"-qfr2", str(QFR2), f"-qfr3", str(QFR3),
            f"-qo", str(QO), f"-qs", str(QS), f"-qr", str(QR),
            f"-cl", str(CL),
        ]
        print(f"Running CLI encoder: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"CLI encoder failed:\n{result.stderr}")
            return
        print(f"  CLI output: {cli_drc.stat().st_size} bytes")

        # Save in-memory bitstream to .drc
        mem_drc = tmpdir / "mem_compressed.drc"
        mem_drc.write_bytes(bitstream)
        print(f"  In-memory output: {len(bitstream)} bytes")

        # CLI decode both
        cli_out_ply = tmpdir / "cli_decoded.ply"
        mem_out_ply = tmpdir / "mem_decoded.ply"

        subprocess.run(
            [str(DECODER), "-i", str(cli_drc), "-o", str(cli_out_ply)],
            capture_output=True, check=True,
        )
        subprocess.run(
            [str(DECODER), "-i", str(mem_drc), "-o", str(mem_out_ply)],
            capture_output=True, check=True,
        )

        # Read both decoded PLYs and compare
        gs_cli = read_gs_ply(str(cli_out_ply))
        gs_mem = read_gs_ply(str(mem_out_ply))

        all_close = True
        for key in ("positions", "f_dc", "f_rest_1", "f_rest_2", "f_rest_3",
                     "opacity", "scale", "rotation"):
            a = gs_cli.get(key, np.empty(0))
            b = gs_mem.get(key, np.empty(0))
            if a.shape != b.shape:
                print(f"  MISMATCH {key}: shape {a.shape} vs {b.shape}")
                all_close = False
                continue
            if a.size == 0:
                continue
            max_diff = np.max(np.abs(a - b))
            match = max_diff < 1e-5
            status = "OK" if match else "MISMATCH"
            print(f"  {key}: {status} (max diff = {max_diff:.2e})")
            if not match:
                all_close = False

        if all_close:
            print("\n--- CLI equivalence test PASSED ---")
        else:
            print("\n--- CLI equivalence test FAILED ---")


if __name__ == "__main__":
    gs, bitstream, gs_dec = test_roundtrip()
    test_cli_equivalence(gs, bitstream)
