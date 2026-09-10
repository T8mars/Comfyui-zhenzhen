import { app } from "../../../scripts/app.js";

const LOW_PRICE_NODE_NAMES = new Set([
    "Comfly_seedance2_low_price",
    "Comfly_seedance25_standard_low_price",
    "Comfly_sd2_seedream_v5_pro_lowprice",
    "Comfly_seedream_v5_pro_layer_decomposition_lowprice",
    "Comfly_zhenzhen_image_g2_lowprice",
    "Comfly_zhenzhen_image_g_v2_lowprice",
    "T8Zhenzhen_Image_G25_LowPrice",
    "T8Zhenzhen_Image_G25_Official",
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
    "T8Zhenzhen_MiniMax_H3_V2_Video_LowPrice",
    "Comfly_hailuo_h3_max_video_lowprice",
    "Comfly_flux3_video_lowprice",
    "Comfly_minimax_h3_ow_video_lowprice",
    "Comfly_minimax_h3_ow_fast_video_lowprice",
    "Comfly_minmax_h3_context_ir_lowprice",
    "Comfly_vidu_q3_video_lowprice",
    "Comfly_vidu_q3_short_play_lowprice",
    "Comfly_fashvsr_video_upscale_lowprice",
    "T8Zhenzhen_VOSR2_Image_Upscale_LowPrice",
    "T8Zhenzhen_VOSR2_Video_Upscale_LowPrice",
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

const WORKSHOP_NODE_NAMES = new Set([
    "OpenAI_Sora_API_Plus",
    "OpenAI_Sora_API",
    "Comfly_Mj",
    "Comfly_upload",
    "Comfly_Mju",
    "Comfly_Mjv",
    "Comfly_Mj_swap_face",
    "Comfly_kling_text2video",
    "Comfly_kling_image2video",
    "Comfly_kling_multi_image2video",
    "Comfly_video_extend",
    "Comfly_lip_sync",
    "ComflyGeminiAPI",
    "ComflySeededit",
    "ComflyChatGPTApi",
    "Comfly_sora2_openai",
    "Comfly_veo_omini",
    "Comfly_sora2",
    "Comfly_sora2_chat",
    "Comfly_sora2_character",
    "Comfly_sora2_new",
    "ComflyJimengApi",
    "Comfly_gpt_image_1_edit",
    "Comfly_gpt_image_1",
    "Comfly_gpt_image_2",
    "Comfly_gpt_image_2_S2A",
    "ComflyJimengVideoApi",
    "Comfly_Flux_Kontext",
    "Comfly_Flux_Kontext_Edit",
    "Comfly_Flux_Kontext_bfl",
    "Comfly_Flux_2_Pro",
    "Comfly_Flux_2_Flex",
    "Comfly_Flux_2_Max",
    "Comfly_Googel_Veo3",
    "Comfly_Googel_Veo3_Lite",
    "ComflyGeminiTextOnly",
    "Comfly_mj_video",
    "Comfly_mj_video_extend",
    "Comfly_qwen_image",
    "Comfly_qwen_image_edit",
    "Comfly_Doubao_Seedream",
    "Comfly_Doubao_Seedream_4",
    "Comfly_Doubao_Seedream_4_5",
    "Comfly_Doubao_Seededit",
    "Comfly_MiniMax_video",
    "Comfly_suno_description",
    "Comfly_suno_lyrics",
    "Comfly_suno_custom",
    "Comfly_suno_upload",
    "Comfly_suno_upload_extend",
    "Comfly_suno_cover",
    "Comfly_vidu_img2video",
    "Comfly_vidu_text2video",
    "Comfly_vidu_ref2video",
    "Comfly_vidu_start-end2video",
    "Comfly_nano_banana",
    "Comfly_nano_banana_fal",
    "Comfly_nano_banana_edit",
    "Comfly_nano_banana2_edit",
    "Comfly_nano_banana2_edit_S2A",
    "Comfly_gemini_3_1_flash_image_edit_S2A",
    "Comfly_Z_image_turbo",
    "ComflyGrok3VideoApi",
    "ComflyGrok3VideoApi30S",
    "Comfly_grok_image",
    "Comfly_LLm_API",
    "Comfly_Doubao_Seedance2_0",
    "Comfly_Doubao_Seedance2_0_Asset",
    "Comfly_gpt_image_2_official",
    "Comfly_gpt_image_2_official_ratio",
    "T8Zhenzhen_GPT_Image_2_5_Workshop",
    "Comfly_gpt_image_2_fal",
    "Comfly_veo3_1_fal",
    "Comfly_seedance2_fal",
    "Comfly_nano_banana_pro_fal",
    "Comfly_nano_banana_2_fal",
    "Comfly_grok_video_fal",
    "Comfly_grok_video_1_5",
    "Comfly_grok_video_1_5_fal",
    "Comfly_sora2_fal",
    "Comfly_gpt_image_2_official_ratio_stable",
    "Comfly_seedream_v5_fal",
    "Comfly_seedream_v5_pro",
    "Comfly_ideogram_v4_fal",
    "Comfly_mai_image_2_5_fal",
    "Comfly_cosmos_3_super_fal",
    "Comfly_hyper3d_rodin_v2_5_fal",
    "Comfly_krea_v2_fal",
    "Comfly_flux_pro_vto_fal",
    "Comfly_heygen_avatar5_fal",
    "Comfly_heygen_avatar4_i2v_fal",
    "Comfly_recraft_v4_1_fal",
    "Comfly_topaz_upscale_fal",
    "Comfly_sonilo_video_to_music_fal",
    "Comfly_mai_image_2_5_edit_fal",
    "Comfly_seed_speech_tts_v2_fal",
    "Comfly_minimax_speech_2_8_fal",
    "Comfly_lyria2_fal",
    "Comfly_bria_fibo_edit_fal",
    "Comfly_grok_video_tools_fal",
    "Comfly_pixverse_v6_fal",
    "Comfly_creatify_aurora_fal",
    "Comfly_veed_fabric_1_0_fal",
    "Comfly_hunyuan_3d_v3_1_pro_fal",
    "Comfly_trellis_2_fal",
    "Comfly_bernini_r_video_fal",
    "Comfly_bernini_r_edit_image_fal",
    "Comfly_luma_ray_v3_2_fal",
    "Comfly_luma_uni_1_v1_fal",
    "Comfly_bria_video_background_removal_v3_fal",
    "Comfly_nemotron_asr_multilingual_fal",
    "Comfly_bria_genfill_v2_fal",
    "Comfly_luma_ray_v3_2_video_to_video_fal",
    "Comfly_pixelcut_video_background_removal_fal",
    "Comfly_sensenova_u1_infographic_fal",
    "Comfly_kling_video_v3_turbo_fal",
    "Comfly_zonos2_fal",
    "Comfly_boogu_image_fal",
]);

const CHANNELS = Object.freeze({
    lowPrice: Object.freeze({
        label: "贞贞的平价小屋APIKEY获取",
        url: "https://api.seedance.nz/sign-up?aff=5f4w",
    }),
    workshop: Object.freeze({
        label: "贞贞的AI工坊APIKEY获取",
        url: "https://ai.t8star.org/register?aff=dP7j",
    }),
});

const BUTTON_MARKER = "zhenzhenApiKeyAcquisitionLink";
const SERIALIZE_GUARD_MARKER = "zhenzhenApiKeySerializeGuard";
const CONFIGURE_GUARD_MARKER = "zhenzhenApiKeyConfigureGuard";
const LEGACY_BUTTON_MARKERS = Object.freeze([
    "zhenzhenImageG2ApiKeyLink",
    "zhenzhenGptImage25ApiKeyLink",
]);

function originalNodeName(name) {
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    const value = String(name ?? "");
    if (value.startsWith(prefix) && value.endsWith(suffix)) {
        return value.slice(prefix.length, -suffix.length);
    }
    return value;
}

function channelForNodeName(name) {
    const originalName = originalNodeName(name);
    if (LOW_PRICE_NODE_NAMES.has(originalName)) {
        return CHANNELS.lowPrice;
    }
    if (WORKSHOP_NODE_NAMES.has(originalName)) {
        return CHANNELS.workshop;
    }
    return null;
}

function isApiKeyButton(widget) {
    return Boolean(
        widget?.[BUTTON_MARKER]
        || LEGACY_BUTTON_MARKERS.some((marker) => widget?.[marker]),
    );
}

function apiKeyButton(node) {
    return node.widgets?.find(isApiKeyButton) ?? null;
}

function removeButtonFromSerializedWidgets(node, serializedNode) {
    const button = apiKeyButton(node);
    const index = button ? node.widgets?.indexOf(button) ?? -1 : -1;
    if (index >= 0 && Array.isArray(serializedNode?.widgets_values)) {
        serializedNode.widgets_values.splice(index, 1);
    }
}

function installSerializationGuard(node) {
    if (node[SERIALIZE_GUARD_MARKER]) {
        return;
    }
    const originalOnSerialize = node.onSerialize;
    node.onSerialize = function (serializedNode) {
        const result = originalOnSerialize?.apply(this, arguments);
        removeButtonFromSerializedWidgets(this, serializedNode);
        return result;
    };
    node[SERIALIZE_GUARD_MARKER] = true;
}

function ensureButtonFits(node) {
    const computed = node.computeSize?.();
    if (!computed || !node.size) {
        return;
    }
    const width = Number(node.size[0]) || Number(computed[0]) || 320;
    const currentHeight = Number(node.size[1]) || 0;
    const requiredHeight = Number(computed[1]) || currentHeight;
    if (requiredHeight > currentHeight) {
        node.setSize?.([width, requiredHeight]);
    }
    node.setDirtyCanvas?.(true, true);
}

function installConfigureGuard(node) {
    if (node[CONFIGURE_GUARD_MARKER]) {
        return;
    }
    const originalOnConfigure = node.onConfigure;
    node.onConfigure = function () {
        const result = originalOnConfigure?.apply(this, arguments);
        ensureButtonFits(this);
        return result;
    };
    node[CONFIGURE_GUARD_MARKER] = true;
}

function installApiKeyButton(node, channel) {
    let button = apiKeyButton(node);
    if (!button) {
        button = node.addWidget("button", channel.label, null, () => {
            window.open(channel.url, "_blank", "noopener,noreferrer");
        });
    }
    button.name = channel.label;
    button.label = channel.label;
    button.callback = () => {
        window.open(channel.url, "_blank", "noopener,noreferrer");
    };
    button.options = { ...(button.options ?? {}), serialize: false };
    button.serialize = false;
    button.serializeValue = () => undefined;
    button[BUTTON_MARKER] = true;
    installSerializationGuard(node);
    installConfigureGuard(node);
    ensureButtonFits(node);
    return button;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.ApiKeyLinks",
    nodeCreated(node) {
        const channel = channelForNodeName(node?.type ?? node?.comfyClass);
        if (channel) {
            installApiKeyButton(node, channel);
        }
    },
});
