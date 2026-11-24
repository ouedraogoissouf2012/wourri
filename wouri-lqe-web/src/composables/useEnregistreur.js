import { onUnmounted, ref } from "vue";

/** Message affiche quand le micro est refuse — ou absent (contexte non securise). */
export const MESSAGE_MICRO_REFUSE = "Micro non autorisé — autorise l'accès au micro dans le navigateur.";

/** Message affiche quand le navigateur ne sait pas enregistrer (MediaRecorder absent). */
export const MESSAGE_ENREGISTREUR_INDISPONIBLE =
  "Ce navigateur ne sait pas enregistrer la voix — essaie avec un navigateur à jour.";

/**
 * Enregistreur de voix partage par la Dictee et la fiche de relecture (ADR-0045,
 * revision du 2026-11-24). Extrait de DictationView sans changement de comportement,
 * a deux exceptions pres, qui ferment chacune un micro reste ouvert :
 *  - un `MediaRecorder` qui leve relache le micro et rend le bouton a nouveau
 *    utilisable (avant : micro ouvert, bouton mort pour de bon) ;
 *  - au demontage de l'ecran, le micro est relache et l'URL de l'extrait revoquee,
 *    y compris si le micro arrive apres le demontage.
 *
 * `demarrer()` ne leve jamais : il rend `{ ok: true }`, `{ ok: false }` quand l'appel
 * est ignore (demarrage deja en cours, enregistrement ou extrait presents), ou
 * `{ ok: false, erreur }` avec le message a montrer au locuteur.
 */
export function useEnregistreur() {
  const enCours = ref(false);
  const extrait = ref(null); // { blob, url, mime }
  let recorder = null;
  let flux = null;
  let demarrage = false; // garde anti-re-entrance : le bouton reste rendu pendant getUserMedia
  let demonte = false;

  function relacherMicro() {
    if (flux) flux.getTracks().forEach((t) => t.stop());
    flux = null;
  }

  function effacer() {
    // revoque l'Object URL avant de perdre la reference (sinon le blob fuit en memoire)
    if (extrait.value && extrait.value.url) URL.revokeObjectURL(extrait.value.url);
    extrait.value = null;
  }

  async function demarrer() {
    if (demarrage || enCours.value || extrait.value) return { ok: false };
    demarrage = true;
    let obtenu;
    try {
      obtenu = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      demarrage = false;
      return { ok: false, erreur: MESSAGE_MICRO_REFUSE };
    }
    if (demonte) {
      obtenu.getTracks().forEach((t) => t.stop());
      return { ok: false };
    }
    let rec;
    try {
      rec = new MediaRecorder(obtenu);
    } catch {
      obtenu.getTracks().forEach((t) => t.stop());
      demarrage = false;
      return { ok: false, erreur: MESSAGE_ENREGISTREUR_INDISPONIBLE };
    }
    flux = obtenu;
    recorder = rec;
    const morceaux = [];
    rec.ondataavailable = (e) => {
      if (e.data && e.data.size) morceaux.push(e.data);
    };
    rec.onstop = () => {
      const mime = rec.mimeType || "audio/webm";
      const blob = new Blob(morceaux, { type: mime });
      extrait.value = { blob, url: URL.createObjectURL(blob), mime };
      relacherMicro();
    };
    rec.start();
    enCours.value = true;
    demarrage = false; // code post-await synchrone : pas de fenetre d'entrelacement
    return { ok: true };
  }

  function arreter() {
    if (recorder && recorder.state !== "inactive") recorder.stop();
    enCours.value = false;
  }

  onUnmounted(() => {
    demonte = true;
    if (recorder && recorder.state !== "inactive") {
      // l'ecran disparait : on ne fabrique pas d'extrait que personne ne verra
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.stop();
    }
    enCours.value = false;
    relacherMicro();
    effacer();
  });

  return { enCours, extrait, demarrer, arreter, effacer };
}
