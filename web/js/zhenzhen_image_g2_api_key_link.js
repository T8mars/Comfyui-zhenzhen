import { app } from "../../../scripts/app.js";

const NODE_NAMES = new Set([
    "Comfly_zhenzhen_image_g2_lowprice",
    "Comfly_zhenzhen_image_g_v2_lowprice",
    "Comfly_zhenzhen_video_g_omni_flash_lowprice",
    "Comfly_zhenzhen_video_gk_v15_lowprice",
    "Comfly_zhenzhen_video_v31_lowprice",
    "Comfly_whisper_1_lowprice",
    "Comfly_zhenzhen_image_gk_v15_lowprice",
]);
const BUTTON_LABEL = "贞贞的平价AI小屋（国内版）ApiKey获取";
const SIGNUP_URL = "https://api.seedance.nz/sign-up?aff=5f4w";

app.registerExtension({
    name: "ComfyuiZhenzhen.ImageG2ApiKeyLink",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_NAMES.has(nodeData.name)) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);

            if (!this.widgets?.some((widget) => widget.zhenzhenImageG2ApiKeyLink)) {
                const button = this.addWidget("button", BUTTON_LABEL, null, () => {
                    window.open(SIGNUP_URL, "_blank", "noopener,noreferrer");
                });
                button.serialize = false;
                button.zhenzhenImageG2ApiKeyLink = true;
            }

            return result;
        };
    },
});
