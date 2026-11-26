"""Interactive, fully local Geriv2 chat."""
from __future__ import annotations

import argparse
from pathlib import Path

import torch

from geri.training.offline import offline_execution
from .runtime import generate, load_promoted_model


def main() -> None:
    parser = argparse.ArgumentParser(prog="geri-chat", description="Chat offline with the promoted Geriv2 SFT model")
    parser.add_argument("--checkpoint", type=Path, default=Path(r"C:\Geriv2-Data\training\runs\promoted-sft.pt"))
    parser.add_argument("--tokenizer", type=Path, default=Path(r"C:\Geriv2-Data\corpus\pretraining\tokenizer\tokenizer.json"))
    parser.add_argument("--pretraining-manifest", type=Path, default=Path(r"C:\Geriv2-Data\corpus\pretraining\processed\manifest.json"))
    parser.add_argument("--sft-manifest", type=Path, default=Path(r"C:\Geriv2-Data\sft\candidate\processed\manifest.json"))
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    args = parser.parse_args()
    torch.set_num_threads(1)
    with offline_execution():
        model, tokenizer = load_promoted_model(args.checkpoint, args.tokenizer, args.pretraining_manifest, args.sft_manifest)
        print("Geri listo (offline). Escribe /clear para reiniciar o /exit para salir.")
        history: list[dict[str, str]] = []
        while True:
            try:
                user_text = input("Tú> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if user_text.lower() in {"/exit", "/quit"}:
                break
            if user_text.lower() == "/clear":
                history.clear()
                print("Historial reiniciado.")
                continue
            if not user_text:
                continue
            history.append({"role": "user", "content": user_text})
            try:
                result = generate(model, tokenizer, history, temperature=args.temperature,
                                  top_k=args.top_k, top_p=args.top_p, max_new_tokens=args.max_new_tokens)
            except Exception:
                history.pop()
                raise
            print(f"Geri> {result['text']}")
            print(f"[{result['tokens']} tokens · {result['tokens_per_second']:.2f} tokens/s · {result['seconds']:.2f} s]")
            if result["text"]:
                history.append({"role": "assistant", "content": result["text"]})
            else:
                history.pop()


if __name__ == "__main__":
    main()
