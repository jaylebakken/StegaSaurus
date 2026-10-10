# Attribution V2 Visuals

These diagrams explain the current repeated-block attribution prototype. They
show retained-record verification and pooled block evidence; they do not claim
unknown-handle discovery, arbitrary crop recovery, codec robustness, or
perceptual transparency.

## 1. Single Block Encoding And Decoding

One 30-second block carries a four-byte opaque registry handle protected by
Reed--Solomon parity. The handle is not user metadata. It is a lookup key for a
retained authenticated registry record.

```mermaid
flowchart LR
    subgraph encode["Encode one 30 s block"]
        cover["30 s PCM block"] --> plan["4-byte handle\n+ 16 RS parity"]
        plan --> bits["Framed + interleaved\ncarrier bits"]
        secret["Master secret"] --> map["Four keyed replica maps\nacross block quarters"]
        bits --> map
        map --> embed["Bias spectral pair magnitudes\nat selected frames"]
        cover --> embed
        embed --> block["Watermarked block"]
        map --> record["Retained AttributionRecord\nhandle, carrier plan,\nprivate frame maps"]
    end

    subgraph decode["Decode one retained block claim"]
        received["Received block"] --> score["Score retained frames\nin four replicas"]
        record --> score
        score --> combine["Weighted score combine\nper carrier position"]
        combine --> decide["carrier 0 / 1 / erasure"]
        decide --> rs["Unframe -> deinterleave\n-> RS recovery"]
        rs --> claim["recovered | mismatch\n| unrecoverable"]
    end

    block --> received

    classDef audio fill:#d9edf7,stroke:#31708f,color:#000;
    classDef private fill:#fcf8e3,stroke:#8a6d3b,color:#000;
    classDef boundary fill:#f2dede,stroke:#a94442,color:#000;
    class cover,block,received audio;
    class record,map private;
    class secret boundary;
```

### Visual Example

```text
30 s block timeline

|---------- replica 1 ----------|---------- replica 2 ----------|---------- replica 3 ----------|---------- replica 4 ----------|
      bit 0  bit 1  bit 2 ...        bit 0  bit 1  bit 2 ...        bit 0  bit 1  bit 2 ...        bit 0  bit 1  bit 2 ...
       +      -      +                +      -      +                +      -      +                +      -      +

For carrier bit 2:
    replica scores:  +0.31, +0.44, erasure, +0.28
    combined score:  +0.36
    observed bit:    1

For carrier bit 7:
    replica scores:  +0.02, -0.01, erasure, +0.00
    combined score:  too weak
    observed bit:    erasure
```

**How to read it**

- The same carrier bit is embedded once in each of four block quarters.
- Weak evidence becomes an erasure instead of a confident guess.
- Reed--Solomon recovery consumes `2 * symbol_errors + symbol_erasures` from the parity budget.
- The retained frame map is private registry material. Without it, this single-block application path is not blind recovery.

## 2. Repeated Block Encoding, Voting, And Pooling

V2 repeats the same handle in each complete block. Verification can make a fast
decision from independent block votes, then use pooled carrier evidence for a
higher-assurance block-distress fallback.

```mermaid
flowchart TD
    song["Song PCM"] --> split["Split into complete 30 s blocks"]
    handle["One issued 4-byte registry handle"] --> b1["Block 1 embed"]
    handle --> b2["Block 2 embed"]
    handle --> b3["Block 3 embed"]
    handle --> b4["Block 4 embed"]
    handle --> b5["Block 5 embed"]
    split --> b1
    split --> b2
    split --> b3
    split --> b4
    split --> b5
    b1 --> watermarked["Concatenate watermarked blocks\ntrailing partial audio unchanged"]
    b2 --> watermarked
    b3 --> watermarked
    b4 --> watermarked
    b5 --> watermarked

    watermarked --> received["Received song"]
    records["Retained BlockAttributionRecord\none record per complete block"] --> verify["Verify available blocks"]
    received --> verify

    verify --> votes["Per-block votes\nrecover / mismatch / unrecoverable"]
    votes --> fast["Fast decision\naccept if enough blocks recover"]

    verify --> evidence["Per-block carrier scores"]
    evidence --> pool["Pool scores by carrier position\nacross repeated blocks"]
    pool --> pooledrs["One pooled RS recovery"]
    pooledrs --> offline["Higher-assurance decision\nfrom pooled evidence"]

    votes --> distress{"Failure type?"}
    distress -->|high pilot + weak block evidence| pool
    distress -->|low localization or timing symptoms| geometry["Geometry fallback\nexperimental blind path"]

    classDef current fill:#d9edf7,stroke:#31708f,color:#000;
    classDef private fill:#fcf8e3,stroke:#8a6d3b,color:#000;
    classDef research fill:#e8e8e8,stroke:#666,color:#000,stroke-dasharray: 5 5;
    class song,split,b1,b2,b3,b4,b5,watermarked,received,verify,votes,fast,evidence,pool,pooledrs,offline current;
    class records private;
    class geometry research;
```

### Visual Example

```text
2.5 minute song as five complete 30 s attribution blocks

| block 1 | block 2 | block 3 | block 4 | block 5 |
| handle A| handle A| handle A| handle A| handle A|

Fast block votes:

| Block | Single-block result | RS cost | Use |
| ---: | --- | ---: | --- |
| 1 | recovered | 4 | vote |
| 2 | recovered | 14 | vote |
| 3 | too costly / weak | 21 | evidence only |
| 4 | too costly / weak | 20 | evidence only |
| 5 | recovered | 3 | vote |

Fast vote result:
    3 recovered blocks -> accept a 2-vote or 3-vote policy

Pooled evidence result:
    combine carrier scores from blocks 1-5
    pooled carrier errors: 0
    pooled erasures:       0
    pooled RS cost:        0
    pooled decision:       recovered
```

**How to read it**

- Block voting answers: "How many independent blocks recovered the same claim?"
- Evidence pooling answers: "Can partial evidence from weak blocks produce one cleaner shared codeword?"
- Geometry fallback is not the first response to weak exact-looking blocks. It is reserved for localization or timing distress.
- Current production code implements retained-record block encoding and pooled verification in `src/stegosaurus/audio/attribution_core/blocks.py`.
- Blind window ranking and non-oracle geometry recovery remain archived experiment paths until promoted behind the same block and pooling contracts.

