(() => {
  const navButtons = Array.from(document.querySelectorAll("[data-view-target]"));
  const views = Array.from(document.querySelectorAll("[data-view]"));
  const jumpButtons = Array.from(document.querySelectorAll("[data-view-jump]"));
  const dropZone = document.querySelector("[data-drop-zone]");
  const fileInput = document.querySelector("[data-file-input]");
  const fileName = document.querySelector("[data-file-name]");
  const resetFile = document.querySelector("[data-reset-file]");
  const stagePackage = document.querySelector("[data-stage-package]");
  const sourceStatus = document.querySelector("[data-source-status]");
  const packageTitle = document.querySelector("[data-package-title]");
  const packageCaption = document.querySelector("[data-package-caption]");
  const packageSteps = Array.from(document.querySelectorAll("[data-package-steps] li"));

  const showView = (id) => {
    views.forEach((view) => {
      view.classList.toggle("is-active", view.id === id);
    });
    navButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.viewTarget === id);
    });
  };

  const setFile = (file) => {
    if (!file) {
      if (fileName) {
        fileName.textContent = "No file selected";
      }
      if (sourceStatus) {
        sourceStatus.textContent = "Waiting for browser file selection.";
      }
      packageSteps.forEach((step, index) => {
        step.classList.toggle("is-ready", index === 0);
        step.classList.remove("is-current");
      });
      if (packageTitle) {
        packageTitle.textContent = "Not staged yet";
      }
      if (packageCaption) {
        packageCaption.textContent = "Choose a WAV file and stage the package when ready.";
      }
      return;
    }

    if (fileName) {
      fileName.textContent = file.name;
    }
    if (sourceStatus) {
      sourceStatus.textContent = `${file.name} is ready for an authenticated song record.`;
    }
    packageSteps.forEach((step, index) => {
      step.classList.toggle("is-ready", index === 0);
      step.classList.toggle("is-current", index === 1);
    });
    if (packageTitle) {
      packageTitle.textContent = "Source ready";
    }
    if (packageCaption) {
      packageCaption.textContent = "Next step: sign in and let the gateway create the song record.";
    }
  };

  navButtons.forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.viewTarget));
  });

  jumpButtons.forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.viewJump));
  });

  if (fileInput) {
    fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
  }

  if (dropZone) {
    dropZone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropZone.classList.add("is-dragging");
    });
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("is-dragging");
    });
    dropZone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropZone.classList.remove("is-dragging");
      setFile(event.dataTransfer.files[0]);
    });
  }

  if (resetFile) {
    resetFile.addEventListener("click", () => {
      if (fileInput) {
        fileInput.value = "";
      }
      setFile(null);
    });
  }

  if (stagePackage) {
    stagePackage.addEventListener("click", () => {
      packageSteps.forEach((step, index) => {
        step.classList.toggle("is-ready", index <= 2);
        step.classList.toggle("is-current", index === 3);
      });
      if (packageTitle) {
        packageTitle.textContent = "Package staged";
      }
      if (packageCaption) {
        packageCaption.textContent = "This is ready for the Cognito plus gateway integration.";
      }
    });
  }
})();
