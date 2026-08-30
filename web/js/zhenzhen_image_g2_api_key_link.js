import { app } from "../../../scripts/app.js";

const NODE_NAMES = new Set([
    "Comfly_seedance2_low_price",
    "Comfly_seedance25_standard_low_price",
    "Comfly_sd2_seedream_v5_pro_lowprice",
    "Comfly_seedream_v5_pro_layer_decomposition_lowprice",
    "Comfly_zhenzhen_image_g2_lowprice",
    "Comfly_zhenzhen_image_g_v2_lowprice",
    "Comfly_zhenzhen_image_nb_lowprice",
    "Comfly_zhenzhen_video_g_omni_flash_lowprice",
    "Comfly_zhenzhen_video_g_omni_flash_lowprice_v2",
    "Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice",
    "Comfly_hunyuan3d_v3_1_lowprice",
    "Comfly_zhenzhen_image_gk_v2_segment_lowprice",
    "Comfly_zhenzhen_image_gk_v2_region_edit_lowprice",
    "Comfly_zhenzhen_video_gk_v15_lowprice",
    "Comfly_zhenzhen_video_v31_lowprice",
    "Comfly_whisper_1_lowprice",
    "Comfly_zhenzhen_image_gk_v15_lowprice",
    "Comfly_happyhorse_1_1_lowprice",
    "Comfly_wan_2_7_spicy_i2v_lowprice",
    "Comfly_wan_3_0_video_lowprice",
    "Comfly_kling_video_lowprice",
    "Comfly_kling_o3_edit_lowprice",
    "Comfly_hailuo_2_3_video_lowprice",
    "Comfly_hailuo_h3_video_lowprice",
    "Comfly_flux3_video_lowprice",
    "Comfly_minimax_h3_ow_video_lowprice",
    "Comfly_minimax_h3_ow_fast_video_lowprice",
    "Comfly_minmax_h3_context_ir_lowprice",
    "Comfly_vidu_q3_video_lowprice",
    "Comfly_vidu_q3_short_play_lowprice",
    "Comfly_fashvsr_video_upscale_lowprice",
    "Comfly_zhenzhen_upscaler_lowprice",
    "Comfly_doubao_seed_audio_1_0_lowprice",
    "Comfly_qwen_image_3_0_lowprice",
    "Comfly_suno_music_lowprice",
    "Comfly_zhenzhen_image_gk_v2_lowprice",
    "Comfly_zhenzhen_image_gk_v2_edit_lowprice",
    "Comfly_wan_2_7_global_image_lowprice",
    "Comfly_qwen3_tts_lowprice",
    "Comfly_minimax_audio_lowprice",
    "Comfly_mureka_bgm_lowprice",
    "Comfly_flowmusic_lowprice",
    "Comfly_midjourney_lowprice",
]);
const BUTTON_LABEL = "贞贞的平价AI小屋（国内版）ApiKey获取";
const SIGNUP_URL = "https://api.seedance.nz/sign-up?aff=5f4w";

function originalNodeName(name) {
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    if (name.startsWith(prefix) && name.endsWith(suffix)) {
        return name.slice(prefix.length, -suffix.length);
    }
    return name;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.ImageG2ApiKeyLink",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_NAMES.has(originalNodeName(nodeData.name))) {
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
