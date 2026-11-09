import { initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, type Auth } from "firebase/auth";

/**
 * Firebase, for "Continue with Google" and nothing else. Accounts with an email and a
 * password never touch it: the Veritas API checks those itself (lib/api.ts).
 *
 * Firebase signs the person in to Google; the app hands the Firebase ID token to the API,
 * gets a Veritas session back, and signs out of Firebase again. The Veritas session is the
 * sign-in, the same as after a password.
 *
 * The web config is public by design: it names the project and grants nothing. It is read
 * from VITE_FIREBASE_* (see .env.example) with no fallback, so a fresh clone never signs
 * people in to somebody else's project; until it is set, the Google button is not shown.
 */
const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const googleAvailable = Boolean(config.apiKey && config.authDomain && config.projectId && config.appId);

export const firebaseApp: FirebaseApp | null = googleAvailable ? initializeApp(config) : null;
export const auth: Auth | null = firebaseApp ? getAuth(firebaseApp) : null;

export const googleProvider = new GoogleAuthProvider();
// Always show the account chooser rather than silently reusing the one signed-in account.
googleProvider.setCustomParameters({ prompt: "select_account" });
