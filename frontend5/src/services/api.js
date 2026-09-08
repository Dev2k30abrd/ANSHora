import axios from "axios";

const API_URL = "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API_URL,
  timeout: 120000,
});

export const uploadDataset = async (file) => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await api.post("/api/dataset/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  // normalize: give the dataset an `id` alias so components don't need
  // to know the backend calls it `dataset_id`
  return { ...response.data, id: response.data.dataset_id };
};

export const getAutoInsights = async (datasetId) => {
  const response = await api.get(`/api/dataset/${datasetId}/insights`);
  return response.data;
};

export const askAgent = async (question, datasetId, history = []) => {
  const response = await api.post("/api/agent/query", {
    question,
    dataset_id: datasetId,
    history: history
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.content })),
  });

  return response.data;
};

export const streamAgentResponse = async (question, datasetId, history, onEvent) => {
  const response = await fetch(`${API_URL}/api/agent/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      dataset_id: datasetId,
      history: (history || [])
        .filter((m) => m.role === "user" || m.role === "assistant")
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.content })),
    }),
  });

  if (!response.ok) {
    let detail = "Failed to start analysis.";
    try {
      const errorBody = await response.json();
      detail = errorBody.detail || detail;
    } catch {
      /* body wasn't JSON, keep default message */
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop();

    for (const eventText of events) {
      if (!eventText.startsWith("data: ")) continue;

      const jsonString = eventText.replace("data: ", "");

      try {
        onEvent(JSON.parse(jsonString));
      } catch (error) {
        console.error("Stream parsing error:", error);
      }
    }
  }
};
