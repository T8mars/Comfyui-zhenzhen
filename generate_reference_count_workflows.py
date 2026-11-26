"""Examples for the updated GK V1.5 and H3 CharSwap reference counts."""

from generate_nov08_workflows import module
from generate_nov17_workflows import finish as finish_video, load, start
from generate_nov19_workflows import finish as finish_image

h3 = module("h3_comfy_low_price_nodes")
nov21 = module("nov21_low_price_nodes")


def example(name, key, values, count, video=False):
    graph, node = start(name, key, values)
    graph["nodes"][0]["pos"] = [30, 40 + (count + int(video)) * 340]
    for i in range(1, count + 1):
        load(graph, node, "image", i)
        graph["nodes"][-1]["pos"] = [30, 40 + (i - 1) * 340]
    if video:
        load(graph, node, "video")
        graph["nodes"][-1]["pos"] = [30, 40 + count * 340]
        finish_video(name, graph, node)
    else:
        finish_image(name, graph, node, "IMAGE")


def main():
    example("zhenzhen-image-gk-v15-edit-5refs-lowprice", "Comfly_zhenzhen_image_gk_v15_lowprice",
            {"model": "zhenzhen-image-gk-v15-edit", "prompt": "Combine the five references into a single cohesive product mood board."}, 5)
    for suffix, key in (("", h3.KEYS["charswap"]), ("-token", nov21.KEYS["charswap"])):
        example(f"zhenzhen-h3-charswap{suffix}-3refs-lowprice", key,
                {"prompt": "Replace the character with the person shown in <Picture 1>, <Picture 2>, and <Picture 3>."}, 3, video=True)


if __name__ == "__main__":
    main()
