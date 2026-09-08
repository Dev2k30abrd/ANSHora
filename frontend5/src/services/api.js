import axios from "axios";

// Production: Uses Vercel environment variable
// Local development: Falls back to localhost
const API_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

console.log("API URL:", API_URL);

const api = axios.create({
  baseURL: API_URL,
  timeout: 120000,
});


// ================================
// UPLOAD DATASET
// ================================

export const uploadDataset = async (file) => {
  const formData = new FormData();

  formData.append("file", file);

  const response = await api.post(
    "/api/dataset/upload",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );

  // Normalize backend response
  return {
    ...response.data,
    id: response.data.dataset_id,
  };
};


// ================================
// AUTO INSIGHTS
// ================================

export const getAutoInsights = async (datasetId) => {
  const response = await api.get(
    `/api/dataset/${datasetId}/insights`
  );

  return response.data;
};


// ================================
// NORMAL AGENT RESPONSE
// ================================

export const askAgent = async (
  question,
  datasetId,
  history = []
) => {
  const response = await api.post(
    "/api/agent/query",
    {
      question,
      dataset_id: datasetId,

      history: history
        .filter(
          (message) =>
            message.role === "user" ||
            message.role === "assistant"
        )
        .slice(-8)
        .map((message) => ({
          role: message.role,
          content: message.content,
        })),
    }
  );

  return response.data;
};


// ================================
// STREAMING AGENT RESPONSE
// ================================

export const streamAgentResponse = async (
  question,
  datasetId,
  history = [],
  onEvent
) => {

  const response = await fetch(
    `${API_URL}/api/agent/stream`,
    {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        question,

        dataset_id: datasetId,

        history: history
          .filter(
            (message) =>
              message.role === "user" ||
              message.role === "assistant"
          )
          .slice(-8)
          .map((message) => ({
            role: message.role,
            content: message.content,
          })),
      }),
    }
  );


  // Handle backend errors
  if (!response.ok) {

    let detail = "Failed to start analysis.";

    try {

      const errorBody =
        await response.json();

      detail =
        errorBody.detail || detail;

    } catch {

      // Response was not JSON

    }

    throw new Error(detail);
  }


  // Ensure streaming is supported
  if (!response.body) {
    throw new Error(
      "Streaming response is not available."
    );
  }


  const reader =
    response.body.getReader();

  const decoder =
    new TextDecoder();

  let buffer = "";


  while (true) {

    const {
      done,
      value,
    } = await reader.read();


    if (done) {
      break;
    }


    buffer += decoder.decode(
      value,
      {
        stream: true,
      }
    );


    // Split SSE events
    const events =
      buffer.split("\n\n");


    // Keep incomplete event
    buffer = events.pop() || "";


    for (const eventText of events) {

      if (
        !eventText.startsWith("data: ")
      ) {
        continue;
      }


      const jsonString =
        eventText.replace(
          "data: ",
          ""
        );


      try {

        const event =
          JSON.parse(jsonString);

        // Send event to React component
        onEvent(event);

      } catch (error) {

        console.error(
          "Stream parsing error:",
          error
        );

      }

    }

  }

};
