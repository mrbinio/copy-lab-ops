/* Copy to firebase-config.js after the Firebase web app exists.
   firebase-config.js is gitignored. Web apiKey is a public client key;
   access is Auth allowlist + Firestore rules + authorized domains. */
window.OPS_CONFIG = {
  owners: ["PUT_DAMIAN_GOOGLE_EMAIL_HERE"],
  viewers: [
    /* "mitch@gmail.com" */
  ],
  firebase: {
    apiKey: "",
    authDomain: "copy-lab-ops.firebaseapp.com",
    projectId: "copy-lab-ops",
    storageBucket: "copy-lab-ops.appspot.com",
    messagingSenderId: "",
    appId: "",
  },
};
