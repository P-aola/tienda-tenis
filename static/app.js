document.querySelectorAll(".copiar").forEach((boton) => {
    boton.addEventListener("click", async () => {
        const textoOriginal = boton.textContent;
        try {
            await navigator.clipboard.writeText(boton.dataset.enlace);
            boton.textContent = "Dirección copiada";
        } catch (_error) {
            boton.textContent = "No se pudo copiar";
        }
        setTimeout(() => {
            boton.textContent = textoOriginal;
        }, 1800);
    });
});
