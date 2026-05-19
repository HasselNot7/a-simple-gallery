const previewInput = document.querySelector("#photo-input");
const previewStrip = document.querySelector("#preview-strip");
const lightbox = document.querySelector("#lightbox");
const lightboxImage = document.querySelector("#lightbox-image");
const lightboxTitle = document.querySelector("#lightbox-title");
const lightboxDescription = document.querySelector("#lightbox-description");
const lightboxMeta = document.querySelector("#lightbox-meta");
const closeLightboxButtons = document.querySelectorAll("[data-close]");
const lightboxTriggers = document.querySelectorAll("[data-lightbox-trigger]");
const deleteForms = document.querySelectorAll("[data-delete-form]");
const timelineNavItems = Array.from(document.querySelectorAll("[data-timeline-nav-item]"));
const timelineSections = Array.from(document.querySelectorAll("[data-timeline-section]"));
const adminDrawer = document.querySelector("[data-admin-drawer]");
const openAdminDrawerButtons = document.querySelectorAll("[data-open-admin-drawer]");
const closeAdminDrawerButtons = document.querySelectorAll("[data-close-admin-drawer]");
const editDrawer = document.querySelector("[data-edit-drawer]");
const openEditDrawerButtons = document.querySelectorAll("[data-open-edit-drawer]");
const closeEditDrawerButtons = document.querySelectorAll("[data-close-edit-drawer]");
const editForm = document.querySelector("[data-edit-form]");
const editNote = document.querySelector("[data-edit-note]");
const editFilename = document.querySelector("[data-edit-filename]");
const editTitleInput = document.querySelector("#edit-photo-title");
const editOriginalNameInput = document.querySelector("#edit-photo-original-name");
const editUploadedAtInput = document.querySelector("#edit-photo-uploaded-at");
const editTakenAtInput = document.querySelector("#edit-photo-taken-at");
const editCameraModelInput = document.querySelector("#edit-photo-camera-model");
const editLensModelInput = document.querySelector("#edit-photo-lens-model");
const editFocalLengthInput = document.querySelector("#edit-photo-focal-length");
const editApertureInput = document.querySelector("#edit-photo-aperture");
const editShutterSpeedInput = document.querySelector("#edit-photo-shutter-speed");
const editIsoInput = document.querySelector("#edit-photo-iso");
const editDescriptionInput = document.querySelector("#edit-photo-description");

let previewUrls = [];
let adminDrawerCloseTimer = null;
let editDrawerCloseTimer = null;

function clearPreviewUrls() {
  previewUrls.forEach((url) => URL.revokeObjectURL(url));
  previewUrls = [];
}

function closeLightbox() {
  if (!lightbox || !lightboxImage) {
    return;
  }

  lightbox.classList.remove("is-open");
  lightbox.setAttribute("aria-hidden", "true");
  lightboxImage.src = "";
  document.body.style.overflow = "";
}

function openLightbox(trigger) {
  if (!lightbox || !lightboxImage || !lightboxTitle || !lightboxDescription || !lightboxMeta) {
    return;
  }

  const fullImage = trigger.dataset.full;
  if (!fullImage) {
    return;
  }

  closeAdminDrawer();
  closeEditDrawer();

  lightboxImage.src = fullImage;
  lightboxImage.alt = trigger.dataset.title || "";
  lightboxTitle.textContent = trigger.dataset.title || "";
  lightboxDescription.textContent = trigger.dataset.description || "";
  lightboxMeta.textContent = trigger.dataset.meta || "";
  lightbox.classList.add("is-open");
  lightbox.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function openAdminDrawer() {
  if (!adminDrawer) {
    return;
  }

  closeLightbox();
  closeEditDrawer();

  if (adminDrawerCloseTimer) {
    window.clearTimeout(adminDrawerCloseTimer);
    adminDrawerCloseTimer = null;
  }

  adminDrawer.hidden = false;
  adminDrawer.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => {
    adminDrawer.classList.add("is-open");
  });
  document.body.style.overflow = "hidden";
}

function closeAdminDrawer() {
  if (!adminDrawer) {
    return;
  }

  adminDrawer.classList.remove("is-open");
  adminDrawer.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";

  adminDrawerCloseTimer = window.setTimeout(() => {
    if (adminDrawer && !adminDrawer.classList.contains("is-open")) {
      adminDrawer.hidden = true;
    }
  }, 220);
}

function openEditDrawer(button) {
  if (
    !editDrawer ||
    !editForm ||
    !editTitleInput ||
    !editOriginalNameInput ||
    !editUploadedAtInput ||
    !editTakenAtInput ||
    !editCameraModelInput ||
    !editLensModelInput ||
    !editFocalLengthInput ||
    !editApertureInput ||
    !editShutterSpeedInput ||
    !editIsoInput ||
    !editDescriptionInput
  ) {
    return;
  }

  closeLightbox();
  closeAdminDrawer();

  if (editDrawerCloseTimer) {
    window.clearTimeout(editDrawerCloseTimer);
    editDrawerCloseTimer = null;
  }

  const photoId = button.dataset.photoId || "";
  editForm.action = photoId ? `/photos/${photoId}/edit` : "";
  editTitleInput.value = button.dataset.photoTitle || "";
  editOriginalNameInput.value = button.dataset.photoOriginalName || "";
  editUploadedAtInput.value = button.dataset.photoUploadedAt || "";
  editTakenAtInput.value = button.dataset.photoTakenAt || "";
  editCameraModelInput.value = button.dataset.photoCameraModel || "";
  editLensModelInput.value = button.dataset.photoLensModel || "";
  editFocalLengthInput.value = button.dataset.photoFocalLength || "";
  editApertureInput.value = button.dataset.photoAperture || "";
  editShutterSpeedInput.value = button.dataset.photoShutterSpeed || "";
  editIsoInput.value = button.dataset.photoIso || "";
  editDescriptionInput.value = button.dataset.photoDescription || "";

  if (editNote) {
    editNote.textContent = "可以修改标题、原文件名、拍摄时间、上传时间和相机参数，修改后会重新参与时间线排序。";
  }

  if (editFilename) {
    const originalName = button.dataset.photoOriginalName || "";
    editFilename.textContent = originalName ? `文件名：${originalName}` : "";
  }

  editDrawer.hidden = false;
  editDrawer.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => {
    editDrawer.classList.add("is-open");
  });
  document.body.style.overflow = "hidden";
}

function closeEditDrawer() {
  if (!editDrawer) {
    return;
  }

  editDrawer.classList.remove("is-open");
  editDrawer.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";

  editDrawerCloseTimer = window.setTimeout(() => {
    if (editDrawer && !editDrawer.classList.contains("is-open")) {
      editDrawer.hidden = true;
    }
  }, 220);
}

function setActiveTimelineItem(targetId) {
  timelineNavItems.forEach((item) => {
    item.classList.toggle("is-active", item.dataset.target === targetId);
  });
}

if (previewInput && previewStrip) {
  previewInput.addEventListener("change", () => {
    clearPreviewUrls();
    previewStrip.innerHTML = "";

    const files = Array.from(previewInput.files || []);
    if (!files.length) {
      return;
    }

    files.forEach((file) => {
      const objectUrl = URL.createObjectURL(file);
      previewUrls.push(objectUrl);

      const item = document.createElement("article");
      item.className = "preview-item";

      const image = document.createElement("img");
      image.src = objectUrl;
      image.alt = file.name;

      const caption = document.createElement("span");
      caption.textContent = file.name;

      item.append(image, caption);
      previewStrip.appendChild(item);
    });
  });
}

lightboxTriggers.forEach((trigger) => {
  trigger.addEventListener("click", () => {
    openLightbox(trigger);
  });
});

closeLightboxButtons.forEach((button) => {
  button.addEventListener("click", closeLightbox);
});

if (lightbox) {
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) {
      closeLightbox();
    }
  });
}

deleteForms.forEach((form) => {
  form.addEventListener("submit", (event) => {
    const title = form.dataset.photoTitle || "这张照片";
    if (!window.confirm(`确定删除「${title}」吗？`)) {
      event.preventDefault();
    }
  });
});

openAdminDrawerButtons.forEach((button) => {
  button.addEventListener("click", openAdminDrawer);
});

closeAdminDrawerButtons.forEach((button) => {
  button.addEventListener("click", closeAdminDrawer);
});

if (adminDrawer) {
  adminDrawer.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    if (event.target.classList.contains("admin-drawer__backdrop")) {
      closeAdminDrawer();
    }
  });
}

openEditDrawerButtons.forEach((button) => {
  button.addEventListener("click", () => {
    openEditDrawer(button);
  });
});

closeEditDrawerButtons.forEach((button) => {
  button.addEventListener("click", closeEditDrawer);
});

if (editDrawer) {
  editDrawer.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }

    if (event.target.classList.contains("edit-drawer__backdrop")) {
      closeEditDrawer();
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (lightbox && lightbox.classList.contains("is-open")) {
      closeLightbox();
    }

    if (adminDrawer && !adminDrawer.hidden) {
      closeAdminDrawer();
    }

    if (editDrawer && !editDrawer.hidden) {
      closeEditDrawer();
    }
  }
});

if (timelineNavItems.length && timelineSections.length) {
  const observer = new IntersectionObserver(
    (entries) => {
      const visibleEntries = entries.filter((entry) => entry.isIntersecting);
      if (!visibleEntries.length) {
        return;
      }

      const topEntry = visibleEntries.sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
      if (topEntry && topEntry.target instanceof HTMLElement) {
        setActiveTimelineItem(topEntry.target.id);
      }
    },
    {
      root: null,
      threshold: [0.18, 0.35, 0.55],
      rootMargin: "-18% 0px -62% 0px",
    },
  );

  timelineSections.forEach((section, index) => {
    observer.observe(section);
    if (index === 0) {
      setActiveTimelineItem(section.id);
    }
  });

  timelineNavItems.forEach((item) => {
    item.addEventListener("click", () => {
      setActiveTimelineItem(item.dataset.target || "");
    });
  });
}
