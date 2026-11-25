"""Create blank-key examples for the two Magi 2 models."""

from generate_nov08_workflows import module
from generate_nov17_workflows import finish, load, start

magi = module("magi2_low_price_nodes")


def main():
    cases = [
        ("t2v", "text", "A small blue cube slowly rotates on a plain white desk.", [], False),
        ("i2v", "frame", "Move smoothly from the first frame to the last, keeping the same subject.", [("image", 1), ("image", 2)], False),
        ("r2v", "reference", "Animate the subject from the image, following the reference clip and rhythm.", [("image", 1), ("video", 1), ("audio", 1)], False),
        ("r2v-concurrent", "reference", "Animate this reference subject in a quiet studio.", [("image", 1)], True),
    ]
    for model in magi.MODELS:
        for suffix, mode, prompt, inputs, parallel in cases:
            key = f"ComflyConcurrent_{magi.KEY}_Submit" if parallel else magi.KEY
            name = f"zhenzhen-{model}-{suffix}-lowprice"
            graph, node = start(name, key, {"model": model, "generation_type": mode, "seconds": 4, "prompt": prompt})
            for offset, (family, index) in enumerate(inputs):
                load(graph, node, family, index)
                graph["nodes"][-1]["pos"] = [30, 40 + offset * 355]
            graph["nodes"][0]["pos"] = [30, 40 + len(inputs) * 355]
            finish(name, graph, node, concurrent=parallel)


if __name__ == "__main__":
    main()
