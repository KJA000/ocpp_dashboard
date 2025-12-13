import axios from "axios";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE,
  // 필요 시 timeout, headers 등 추가
  timeout: 10000,
});

// 간단 로깅(선택)
api.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error("API Error:", err?.response?.status, err?.message);
    return Promise.reject(err);
  }
);

export default api;
