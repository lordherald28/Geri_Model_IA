"""Small decoder-only Transformer for offline next-token training."""
from __future__ import annotations

import torch
from torch import nn


class CausalSelfAttention(nn.Module):
    def __init__(self, d_model: int, n_heads: int, max_seq_len: int, dropout: float):
        super().__init__()
        if d_model % n_heads:
            raise ValueError("d_model must be divisible by n_heads")
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.output = nn.Linear(d_model, d_model, bias=False)
        self.dropout = dropout
        self.register_buffer("causal_mask", torch.tril(torch.ones(max_seq_len, max_seq_len, dtype=torch.bool)), persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch, length, width = x.shape
        q, k, v = self.qkv(x).view(batch, length, 3, self.n_heads, self.head_dim).unbind(2)
        q, k, v = (t.transpose(1, 2) for t in (q, k, v))
        result = nn.functional.scaled_dot_product_attention(
            q, k, v, attn_mask=self.causal_mask[:length, :length],
            dropout_p=self.dropout if self.training else 0.0,
        )
        return self.output(result.transpose(1, 2).contiguous().view(batch, length, width))


class TransformerBlock(nn.Module):
    def __init__(self, config: dict):
        super().__init__()
        width = config["d_model"]
        self.norm1 = nn.LayerNorm(width)
        self.attention = CausalSelfAttention(width, config["n_heads"], config["max_seq_len"], config["dropout"])
        self.norm2 = nn.LayerNorm(width)
        self.feed_forward = nn.Sequential(
            nn.Linear(width, config["d_ff"]), nn.GELU(), nn.Linear(config["d_ff"], width), nn.Dropout(config["dropout"])
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attention(self.norm1(x))
        return x + self.feed_forward(self.norm2(x))


class GeriTransformer(nn.Module):
    def __init__(self, config: dict):
        super().__init__()
        self.config = dict(config)
        self.token_embedding = nn.Embedding(config["vocab_size"], config["d_model"])
        self.position_embedding = nn.Embedding(config["max_seq_len"], config["d_model"])
        self.blocks = nn.ModuleList(TransformerBlock(config) for _ in range(config["n_layers"]))
        self.final_norm = nn.LayerNorm(config["d_model"])
        self.lm_head = nn.Linear(config["d_model"], config["vocab_size"], bias=False)
        self.lm_head.weight = self.token_embedding.weight
        self.apply(self._initialize)

    @staticmethod
    def _initialize(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
        elif isinstance(module, nn.LayerNorm):
            nn.init.ones_(module.weight)
            nn.init.zeros_(module.bias)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        if tokens.ndim != 2 or tokens.shape[1] > self.config["max_seq_len"]:
            raise ValueError("expected [batch, sequence] within max_seq_len")
        positions = torch.arange(tokens.shape[1], device=tokens.device)
        hidden = self.token_embedding(tokens) + self.position_embedding(positions)
        for block in self.blocks:
            hidden = block(hidden)
        return self.lm_head(self.final_norm(hidden))

    def parameter_count(self) -> int:
        return sum(p.numel() for p in self.parameters())
