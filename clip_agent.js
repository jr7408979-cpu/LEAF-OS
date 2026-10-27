"use strict";

(function () {
  const ClipAgent = {
    name: "Clip Agent",
    version: "0.1.0",

    getStatus() {
      return {
        ready: true,
        capability: "video-task-preparation",
        message: "Clip Agent está listo para recibir tareas."
      };
    },

    validateVideoUrl(url) {
      if (typeof url !== "string" || !url.trim()) {
        return {
          success: false,
          message: "Introduce un enlace de video."
        };
      }

      try {
        const parsed = new URL(url.trim());

        if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
          return {
            success: false,
            message: "El enlace debe usar HTTP o HTTPS."
          };
        }

        return {
          success: true,
          url: parsed.href
        };
      } catch {
        return {
          success: false,
          message: "El enlace no tiene un formato válido."
        };
      }
    }
  };

  window.LEAF_CLIP_AGENT = ClipAgent;
})();
