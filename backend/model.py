"""Chest X-ray classifier (pretrained DenseNet121 from TorchXRayVision) + Grad-CAM."""
import numpy as np
import torch
import torchvision
import torchxrayvision as xrv
from matplotlib import cm
from PIL import Image


class XRayModel:
    def __init__(self, weights: str = "densenet121-res224-all"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # The Render free instance has a 512 MiB memory limit. Inference does not
        # train the network, so freeze parameters to avoid allocating parameter gradients.
        torch.set_num_threads(1)
        self.model = xrv.models.DenseNet(weights=weights).to(self.device).eval()
        self.model.requires_grad_(False)
        self.pathologies = list(self.model.pathologies)
        self.tf = torchvision.transforms.Compose(
            [xrv.datasets.XRayCenterCrop(), xrv.datasets.XRayResizer(224)]
        )

    def preprocess(self, pil_img: Image.Image):
        img = np.array(pil_img.convert("L")).astype(np.float32)
        img = xrv.datasets.normalize(img, 255)[None, ...]  # (1, H, W)
        img = self.tf(img)  # (1, 224, 224)
        return torch.from_numpy(img).unsqueeze(0).to(self.device), img[0]

    @torch.no_grad()
    def predict(self, x: torch.Tensor, top_k: int = 5):
        probs = self.model(x)[0].cpu().numpy()
        pairs = [
            (name, float(p))
            for name, p in zip(self.pathologies, probs)
            if name  # some label slots are empty strings
        ]
        pairs.sort(key=lambda t: t[1], reverse=True)
        return pairs[:top_k]

    def gradcam(self, x: torch.Tensor, label: str) -> np.ndarray:
        """Grad-CAM on the last DenseNet feature map; returns a 224x224 map in [0, 1]."""
        idx = self.pathologies.index(label)
        store = {}

        def hook(_, __, out):
            out.retain_grad()
            store["a"] = out

        handle = self.model.features.register_forward_hook(hook)
        x = x.detach().clone().requires_grad_(True)
        try:
            self.model.zero_grad(set_to_none=True)
            self.model(x)[0, idx].backward()
        finally:
            handle.remove()

        a, g = store["a"], store["a"].grad
        weights = g.mean(dim=(2, 3), keepdim=True)
        cam = torch.relu((weights * a).sum(dim=1))[0].detach().cpu().numpy()
        cam -= cam.min()
        cam /= cam.max() + 1e-8
        cam = np.array(Image.fromarray((cam * 255).astype(np.uint8)).resize((224, 224)))
        return cam / 255.0

    @staticmethod
    def overlay(gray_224: np.ndarray, cam: np.ndarray, alpha: float = 0.45) -> Image.Image:
        g = gray_224 - gray_224.min()
        g = g / (g.max() + 1e-8)
        base = np.stack([g] * 3, axis=-1)
        heat = cm.jet(cam)[..., :3]
        out = (1 - alpha) * base + alpha * heat
        return Image.fromarray((out * 255).astype(np.uint8)).resize((448, 448))
