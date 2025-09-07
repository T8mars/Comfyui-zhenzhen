import numpy as np
import torch
from PIL import Image
from typing import List, Union

def pil2tensor(image: Union[Image.Image, List[Image.Image]]) -> torch.Tensor:
    """
    Convert PIL image(s) to tensor, matching ComfyUI's implementation.
    
    Args:
        image: Single PIL Image or list of PIL Images
        
    Returns:
        torch.Tensor: Image tensor with values normalized to [0, 1]
    """
    if isinstance(image, list):
        if len(image) == 0:
            return torch.empty(0)
        return torch.cat([pil2tensor(img) for img in image], dim=0)

    # Convert PIL image to RGB if needed
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    # Convert to numpy array and normalize to [0, 1]
    img_array = np.array(image).astype(np.float32) / 255.0
    
    # Return tensor with shape [1, H, W, 3]
    return torch.from_numpy(img_array)[None,]

def tensor2pil(image: torch.Tensor) -> List[Image.Image]:
    """
    Convert tensor to PIL image(s), matching ComfyUI's implementation.
    
    Args:
        image: Tensor with shape [B, H, W, 3] or [H, W, 3], values in range [0, 1]
        
    Returns:
        List[Image.Image]: List of PIL Images
    """
    batch_count = image.size(0) if len(image.shape) > 3 else 1
    if batch_count > 1:
        out = []
        for i in range(batch_count):
            out.extend(tensor2pil(image[i]))
        return out

    # Convert tensor to numpy array, scale to [0, 255], and clip values
    numpy_image = np.clip(255.0 * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8)
    
    # Convert numpy array to PIL Image
    return [Image.fromarray(numpy_image)]