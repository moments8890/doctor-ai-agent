import { patientRequest, apiUrl, readError } from "./base";

export async function patientSession(doctorId, patientName) {
  return fetch(apiUrl("/api/patient/session"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId, patient_name: patientName }),
  }).then(async (res) => {
    if (!res.ok) {
      const err = new Error(await readError(res));
      err.status = res.status;
      throw err;
    }
    return res.json();
  });
}

export async function getPatientMe(patientToken) {
  return patientRequest("/api/patient/me", patientToken);
}

export async function getPatientRecords(patientToken) {
  return patientRequest("/api/patient/records", patientToken);
}

export async function sendPatientMessage(patientToken, text) {
  return patientRequest("/api/patient/message", patientToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}
