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
  const sessionStatus = document.querySelector("[data-session-status]");
  const accountTabs = Array.from(document.querySelectorAll("[data-account-mode]"));
  const accountForm = document.querySelector("[data-account-form]");
  const accountTitle = document.querySelector("[data-account-title]");
  const accountCopy = document.querySelector("[data-account-copy]");
  const accountSubmit = document.querySelector("[data-account-submit]");
  const accountStatus = document.querySelector("[data-account-status]");
  const nameField = document.querySelector("[data-name-field]");
  const passwordField = document.querySelector("[data-password-field]");
  const signOut = document.querySelector("[data-sign-out]");
  const statusActions = Array.from(document.querySelectorAll("[data-status-action]"));
  const actionStatus = document.querySelector("[data-action-status]");
  const config = window.SAURUS_CONFIG || {};
  const authStateKey = "saurus_auth_state";
  const pkceKey = "saurus_pkce_verifier";
  const tokenKey = "saurus_tokens";
  let isSignedIn = false;
  let currentFile = null;
  let currentSong = null;

  const accountModes = {
    signin: {
      title: "Welcome back",
      copy: "Use the email connected to your Saurus workspace.",
      submit: "Sign in",
      status: "Sign in opens the secure Saurus account page.",
      showName: false,
      showPassword: true,
    },
    create: {
      title: "Create your workspace",
      copy: "Start with an email, then verify it before adding music.",
      submit: "Create account",
      status: "Account creation opens the secure Saurus account page.",
      showName: true,
      showPassword: true,
    },
    recover: {
      title: "Recover access",
      copy: "Enter your email and we will prepare a reset flow.",
      submit: "Send reset link",
      status: "Recovery opens the secure Saurus account page.",
      showName: false,
      showPassword: false,
    },
  };

  const showView = (id) => {
    if (!isSignedIn && id !== "account") {
      setAccountMode("signin");
      if (accountStatus) {
        accountStatus.textContent = "Sign in or create an account before opening the workspace.";
      }
      id = "account";
    }
    views.forEach((view) => {
      view.classList.toggle("is-active", view.id === id);
    });
    navButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.viewTarget === id);
    });
  };

  const setAccountMode = (mode) => {
    const nextMode = accountModes[mode] ? mode : "signin";
    const copy = accountModes[nextMode];
    accountTabs.forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.accountMode === nextMode);
    });
    if (accountTitle) {
      accountTitle.textContent = copy.title;
    }
    if (accountCopy) {
      accountCopy.textContent = copy.copy;
    }
    if (accountSubmit) {
      accountSubmit.textContent = copy.submit;
    }
    if (accountStatus) {
      accountStatus.textContent = copy.status;
    }
    if (nameField) {
      nameField.hidden = !copy.showName;
    }
    if (passwordField) {
      passwordField.hidden = !copy.showPassword;
    }
  };

  const randomString = () => {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };

  const sha256Base64Url = async (text) => {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return btoa(String.fromCharCode(...new Uint8Array(digest))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };

  const authUrl = async (path) => {
    const state = randomString();
    const verifier = randomString();
    sessionStorage.setItem(authStateKey, state);
    sessionStorage.setItem(pkceKey, verifier);
    const params = new URLSearchParams({
      client_id: config.clientId || "",
      response_type: "code",
      scope: "openid email profile",
      redirect_uri: config.redirectUri || window.location.href.split("?")[0],
      state,
      code_challenge_method: "S256",
      code_challenge: await sha256Base64Url(verifier),
    });
    return `${config.authDomain}${path}?${params.toString()}`;
  };

  const beginHostedAuth = async (mode) => {
    if (!config.authDomain || !config.clientId) {
      if (accountStatus) {
        accountStatus.textContent = "Account configuration is not available yet.";
      }
      return;
    }
    const path = mode === "create" ? "/signup" : mode === "recover" ? "/forgotPassword" : "/login";
    window.location.assign(await authUrl(path));
  };

  const exchangeCode = async () => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    if (!code) {
      return;
    }
    const expectedState = sessionStorage.getItem(authStateKey);
    const verifier = sessionStorage.getItem(pkceKey);
    window.history.replaceState({}, document.title, window.location.pathname);
    if (!state || state !== expectedState || !verifier) {
      throw new Error("Sign-in response could not be matched to this browser session.");
    }
    const body = new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      code,
      redirect_uri: config.redirectUri,
      code_verifier: verifier,
    });
    const response = await fetch(`${config.authDomain}/oauth2/token`, {
      method: "POST",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body,
    });
    if (!response.ok) {
      throw new Error("Sign-in token exchange failed.");
    }
    const tokens = await response.json();
    localStorage.setItem(tokenKey, JSON.stringify(tokens));
    sessionStorage.removeItem(authStateKey);
    sessionStorage.removeItem(pkceKey);
    isSignedIn = true;
    if (sessionStatus) {
      sessionStatus.textContent = "Signed in";
    }
    if (accountStatus) {
      accountStatus.textContent = "Signed in. Your workspace is ready.";
    }
    showView("app");
  };

  const tokens = () => {
    const raw = localStorage.getItem(tokenKey);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch {
      localStorage.removeItem(tokenKey);
      return null;
    }
  };

  const apiRequest = async (path, options = {}) => {
    const stored = tokens();
    if (!stored?.id_token && !stored?.access_token) {
      throw new Error("Please sign in before preparing a copy.");
    }
    if (!config.apiBaseUrl) {
      throw new Error("The Saurus API is not connected yet.");
    }
    const requestId = crypto.randomUUID();
    const response = await fetch(`${config.apiBaseUrl}${path}`, {
      ...options,
      headers: {
        "Authorization": `Bearer ${stored.id_token || stored.access_token}`,
        "Content-Type": "application/json",
        "Idempotency-Key": requestId,
        "X-Request-ID": requestId,
        ...(options.headers || {}),
      },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.error?.message || `Request failed with ${response.status}`);
    }
    return body;
  };

  const fileDigest = async (file) => {
    const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
  };

  const setFile = (file) => {
    if (!file) {
      currentFile = null;
      if (fileName) {
        fileName.textContent = "No file selected";
      }
      if (sourceStatus) {
        sourceStatus.textContent = "Waiting for a WAV file.";
      }
      packageSteps.forEach((step, index) => {
        step.classList.toggle("is-ready", index === 0);
        step.classList.remove("is-current");
      });
      if (packageTitle) {
        packageTitle.textContent = "Not prepared yet";
      }
      if (packageCaption) {
        packageCaption.textContent = "Choose a WAV file, then prepare the copy.";
      }
      return;
    }

    currentFile = file;
    if (fileName) {
      fileName.textContent = file.name;
    }
    if (sourceStatus) {
      sourceStatus.textContent = `${file.name} is ready.`;
    }
    packageSteps.forEach((step, index) => {
      step.classList.toggle("is-ready", index === 0);
      step.classList.toggle("is-current", index === 1);
    });
    if (packageTitle) {
      packageTitle.textContent = "Track ready";
    }
    if (packageCaption) {
      packageCaption.textContent = "Next step: create the private song page.";
    }
  };

  navButtons.forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.viewTarget));
  });

  accountTabs.forEach((tab) => {
    tab.addEventListener("click", () => setAccountMode(tab.dataset.accountMode));
  });

  if (accountForm) {
    accountForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const activeMode = accountTabs.find((tab) => tab.classList.contains("is-active"))?.dataset.accountMode || "signin";
      if (accountStatus) {
        accountStatus.textContent = activeMode === "recover" ? "Opening account recovery..." : "Opening secure account page...";
      }
      beginHostedAuth(activeMode).catch((error) => {
        if (accountStatus) {
          accountStatus.textContent = error.message;
        }
      });
    });
  }

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
    stagePackage.addEventListener("click", async () => {
      try {
        if (!currentFile) {
          throw new Error("Choose a WAV file before preparing a copy.");
        }
        if (packageTitle) {
          packageTitle.textContent = "Creating song page";
        }
        if (packageCaption) {
          packageCaption.textContent = "Sending the track details to Saurus...";
        }
        const title = document.querySelector("input[aria-label='Track title']")?.value || currentFile.name.replace(/\.wav$/i, "");
        const recipient = document.querySelector("input[aria-label='Recipient or list name']")?.value || "Review recipient";
        const songBody = await apiRequest("/v1/songs", {
          method: "POST",
          body: JSON.stringify({
            title,
            source_digest: await fileDigest(currentFile),
            sample_rate: 44100,
            sample_count: Math.max(1, Math.floor(currentFile.size / 4)),
            fingerprint_version: "browser-alpha-v1",
          }),
        });
        currentSong = songBody.song;
        packageSteps.forEach((step, index) => {
          step.classList.toggle("is-ready", index <= 1);
          step.classList.toggle("is-current", index === 2);
        });
        if (packageTitle) {
          packageTitle.textContent = "Reserving recipient copy";
        }
        const exportBody = await apiRequest(`/v1/songs/${currentSong.song_id}/exports:reserve`, {
          method: "POST",
          body: JSON.stringify({recipient_label: recipient}),
        });
        packageSteps.forEach((step, index) => {
          step.classList.toggle("is-ready", index <= 2);
          step.classList.toggle("is-current", index === 3);
        });
        if (packageTitle) {
          packageTitle.textContent = "Copy prepared";
        }
        if (packageCaption) {
          packageCaption.textContent = `Reserved ${exportBody.export.export_id}. Local audio marking is the next step.`;
        }
      } catch (error) {
        if (packageTitle) {
          packageTitle.textContent = "Could not prepare copy";
        }
        if (packageCaption) {
          packageCaption.textContent = error.message;
        }
      }
    });
  }

  if (signOut) {
    signOut.addEventListener("click", () => {
      if (sessionStatus) {
        sessionStatus.textContent = "Signed out";
      }
      isSignedIn = false;
      localStorage.removeItem(tokenKey);
      showView("account");
      setAccountMode("signin");
      if (accountStatus) {
        accountStatus.textContent = "Signed out. Sign in again before adding music.";
      }
    });
  }

  statusActions.forEach((button) => {
    button.addEventListener("click", () => {
      if (actionStatus) {
        actionStatus.textContent = button.dataset.statusAction;
      }
    });
  });

  if (tokens()) {
    isSignedIn = true;
    if (sessionStatus) {
      sessionStatus.textContent = "Signed in";
    }
  }

  exchangeCode().catch((error) => {
    if (accountStatus) {
      accountStatus.textContent = error.message;
    }
  });
})();
