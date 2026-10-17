(() => {
  const root = document.documentElement;
  root.classList.add("js");

  const header = document.querySelector(".site-header");
  const revealTargets = document.querySelectorAll("[data-reveal]");
  const tiltTargets = document.querySelectorAll("[data-tilt]");
  const parallaxTargets = document.querySelectorAll("[data-parallax]");
  const storySections = Array.from(document.querySelectorAll("[data-story-stage]"));
  const processDock = document.querySelector("[data-process-dock]");
  const processTitle = document.querySelector("[data-process-title]");
  const processCaption = document.querySelector("[data-process-caption]");
  const processSteps = document.querySelectorAll("[data-process-step]");
  const processNodes = document.querySelectorAll("[data-process-node]");
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let ticking = false;
  let activeStage = -1;

  const processCopy = [
    {
      title: "Register clean master",
      caption: "The clean master becomes a private song record.",
    },
    {
      title: "Create traced exports",
      caption: "Each authorized copy receives its own registry-backed handle.",
    },
    {
      title: "Localize leaked excerpt",
      caption: "The suspicious clip is aligned against the known source song.",
    },
    {
      title: "Verify export match",
      caption: "Candidate export records compete until evidence accepts or abstains.",
    },
    {
      title: "Review lineage",
      caption: "The registry reconstructs recipient context and parent-child history.",
    },
  ];

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const setProcessStage = (stage) => {
    if (!processDock || stage === activeStage) {
      return;
    }

    activeStage = stage;
    processDock.dataset.stage = String(stage);

    if (processTitle) {
      processTitle.textContent = processCopy[stage].title;
    }

    if (processCaption) {
      processCaption.textContent = processCopy[stage].caption;
    }

    processSteps.forEach((step) => {
      const stepStage = Number(step.dataset.processStep);
      step.classList.toggle("is-active", stepStage === stage);
      step.classList.toggle("is-complete", stepStage < stage);
    });

    processNodes.forEach((node) => {
      const nodeStage = Number(node.dataset.processNode);
      node.classList.toggle("is-active", nodeStage === stage);
      node.classList.toggle("is-complete", nodeStage < stage);
    });
  };

  const updateProcessStage = () => {
    if (!storySections.length) {
      return;
    }

    const anchor = window.innerHeight * 0.42;
    let nextStage = Number(storySections[0].dataset.storyStage);

    storySections.forEach((section) => {
      const rect = section.getBoundingClientRect();
      if (rect.top <= anchor) {
        nextStage = Number(section.dataset.storyStage);
      }
    });

    setProcessStage(clamp(nextStage, 0, processCopy.length - 1));
  };

  const updateScrollState = () => {
    const availableScroll = Math.max(document.body.scrollHeight - window.innerHeight, 1);
    const progress = clamp(window.scrollY / availableScroll, 0, 1);

    root.style.setProperty("--page-progress", progress.toFixed(4));
    root.style.setProperty("--ambient-shift", `${Math.round(progress * 360)}px`);
    root.style.setProperty("--ambient-grid-shift", `${Math.round(progress * -86)}px`);
    root.style.setProperty(
      "--ambient-photo-shift",
      motionQuery.matches ? "0px" : `${Math.round(progress * -170)}px`,
    );
    root.style.setProperty(
      "--ambient-wave-shift",
      motionQuery.matches ? "0px" : `${Math.round(progress * -120)}px`,
    );
    root.style.setProperty("--shine-shift", `${Math.round(progress * 180)}%`);

    parallaxTargets.forEach((target) => {
      const speed = Number(target.dataset.parallaxSpeed || "0");
      const rect = target.getBoundingClientRect();
      const distanceFromCenter = rect.top + rect.height / 2 - window.innerHeight / 2;
      const shift = motionQuery.matches ? 0 : clamp(distanceFromCenter * speed, -80, 80);
      target.style.setProperty("--parallax-y", `${shift.toFixed(1)}px`);
    });

    if (header) {
      header.classList.toggle("is-scrolled", window.scrollY > 18);
    }

    updateProcessStage();
    ticking = false;
  };

  const revealVisibleTargets = () => {
    revealTargets.forEach((target) => {
      const rect = target.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.92 && rect.bottom > 0) {
        target.classList.add("is-visible");
      }
    });
  };

  const scheduleScrollUpdate = () => {
    if (!ticking) {
      window.requestAnimationFrame(updateScrollState);
      ticking = true;
    }
  };

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.12 },
    );

    revealTargets.forEach((target) => observer.observe(target));
  } else {
    revealTargets.forEach((target) => target.classList.add("is-visible"));
  }

  tiltTargets.forEach((target) => {
    target.addEventListener("pointermove", (event) => {
      if (motionQuery.matches) {
        return;
      }

      const rect = target.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;

      target.style.setProperty("--tilt-x", `${clamp(y * -5, -5, 5).toFixed(2)}deg`);
      target.style.setProperty("--tilt-y", `${clamp(x * 6, -6, 6).toFixed(2)}deg`);
    });

    target.addEventListener("pointerleave", () => {
      target.style.setProperty("--tilt-x", "0deg");
      target.style.setProperty("--tilt-y", "0deg");
    });
  });

  window.addEventListener("scroll", scheduleScrollUpdate, { passive: true });
  window.addEventListener("resize", scheduleScrollUpdate);
  revealVisibleTargets();
  updateScrollState();
})();
