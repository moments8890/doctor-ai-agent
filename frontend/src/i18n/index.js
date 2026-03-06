import zhCN from "./zhCN";

const DICTS = {
  "zh-CN": zhCN,
};

let locale = "zh-CN";

function getByPath(obj, path) {
  return path.split(".").reduce((curr, key) => (curr && curr[key] !== undefined ? curr[key] : undefined), obj);
}

function interpolate(template, params) {
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    if (params[key] === undefined || params[key] === null) return "";
    return String(params[key]);
  });
}

export function setLocale(nextLocale) {
  if (DICTS[nextLocale]) locale = nextLocale;
}

export function getLocale() {
  return locale;
}

export function t(key, params = {}) {
  const dict = DICTS[locale] || DICTS["zh-CN"];
  const value = getByPath(dict, key);
  if (typeof value === "string") return interpolate(value, params);
  return key;
}

export function traw(key) {
  const dict = DICTS[locale] || DICTS["zh-CN"];
  const value = getByPath(dict, key);
  return value === undefined ? key : value;
}

