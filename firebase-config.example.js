/* Copy to firebase-config.js after the Firebase web app exists.
   firebase-config.js is gitignored. Merge into OPS_CONFIG — do not wipe access-config.js. */
window.OPS_CONFIG = window.OPS_CONFIG || {};
window.OPS_CONFIG.owners = ["damianbiniarz@gmail.com"];
window.OPS_CONFIG.viewers = ["mitchell@vinnland.se"];
window.OPS_CONFIG.firebase = {
  apiKey: "",
  authDomain: "copy-lab-ops.firebaseapp.com",
  projectId: "copy-lab-ops",
  storageBucket: "copy-lab-ops.appspot.com",
  messagingSenderId: "",
  appId: "",
};
