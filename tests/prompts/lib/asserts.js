// Assertion helpers for PromptFoo. Each exported function matches
// promptfoo's signature: (output, context) -> {pass, reason}.
//
// Why this shape: promptfoo's `type: javascript` sandbox doesn't
// expose require(), so the inline helper approach doesn't work. But
// `value: file://lib/asserts.js:fnName` IS supported — promptfoo
// loads the file and calls the named export.
//
// Usage in cases YAML:
//   - type: javascript
//     value: file://lib/asserts.js:case0_aneurysm_size

function normalize(s) {
  if (!s) return "";
  return String(s)
    .replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(/[Ａ-Ｚ]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(/[ａ-ｚ]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(/[，、；]/g, ",")
    .replace(/[。．]/g, ".")
    .replace(/[：]/g, ":")
    .replace(/[（]/g, "(").replace(/[）]/g, ")")
    .replace(/[×xX*]/g, "×")
    .replace(/[\s　]+/g, "")
    .replace(/[,:()]/g, "");
}

function includesNormalized(haystack, needle) {
  return normalize(haystack).includes(normalize(needle));
}
function includesAll(haystack, needles) {
  const h = normalize(haystack);
  return needles.every(n => h.includes(normalize(n)));
}
function includesAny(haystack, needles) {
  const h = normalize(haystack);
  return needles.some(n => h.includes(normalize(n)));
}
function anyFieldIncludesAll(obj, fields, needles) {
  return fields.some(f => includesAll(obj[f] || "", needles));
}

// Parse the model output (JSON). Returns null on parse failure.
function parseObj(output) {
  try { return JSON.parse(output); } catch { return null; }
}

// Each assertion below exported as a named function. Promptfoo
// `file://lib/asserts.js:name` invokes it with (output, context).

module.exports = {
  // Case 0 — 详细主治医师
  case0_aneurysm_size(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['右侧颈内动脉后交通段动脉瘤', '6mm×5mm']);
  },

  // Case 1 — SAH急诊
  case1_ACoA_SAH(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesNormalized(obj.present_illness, '前交通动脉瘤破裂SAH');
  },
  case1_ACoA_size(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['ACoA动脉瘤', '5mm×4mm', '瘤颈2.5mm']);
  },
  case1_GCS(output) {
    const obj = parseObj(output); if (!obj) return false;
    // LLM inserts "术前" between GCS and the score: "GCS术前E2V2M5=9".
    // Split into two needles so insertions between them don't break the match.
    return anyFieldIncludesAll(obj, ['physical_exam', 'present_illness', 'specialist_exam'], ['GCS', 'E2V2M5=9']);
  },

  // Case 2 — OCR粘贴
  case2_chief_complaint(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.chief_complaint, ['反复头晕', '右侧肢体麻木', '2月', '加重', '3天']);
  },
  case2_ICA_stenosis(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['左侧颈内动脉C6段重度狭窄', '85%']);
  },
  case2_ulcerated_plaque(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAny(obj.present_illness, ['伴溃疡斑块形成', '伴有溃疡斑块形成', '溃疡斑块']);
  },
  case2_gait(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['右下肢', '拖曳']);
  },
  case2_neck_traction(output) {
    const obj = parseObj(output); if (!obj) return false;
    const pi = obj.present_illness || '';
    return includesAll(pi, ['颈椎病', '牵引']) &&
           includesAny(pi, ['无效', '无明显缓解', '症状无缓解', '缓解']);
  },

  // Case 3 — 多轮口述
  case3_AVM_location(output) {
    const obj = parseObj(output); if (!obj) return false;
    const pi = obj.present_illness || '';
    return includesAll(pi, ['左侧额顶叶']) &&
           includesAny(pi, ['AVM', '脑动静脉畸形', '动静脉畸形']);
  },
  case3_headache_worsening(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['1周前', '头痛加重', '持续性']);
  },
  case3_blurred_vision(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAny(obj.present_illness, ['伴视物模糊', '伴有视物模糊', '视物模糊']);
  },

  // Case 5 — 否定为主随访
  case5_followup_3m(output) {
    const obj = parseObj(output); if (!obj) return false;
    // LLM may say "动脉瘤介入栓塞术后" (extra 介入) — don't require
    // contiguous "动脉瘤栓塞". Check the key clinical tokens.
    const fields = ['auxiliary_exam', 'chief_complaint', 'orders_followup', 'present_illness', 'treatment_plan'];
    return anyFieldIncludesAll(obj, fields, ['栓塞', '术后', '3', '复查']);
  },
  case5_sah_history(output) {
    const obj = parseObj(output); if (!obj) return false;
    const pi = obj.present_illness || '';
    return includesAll(pi, ['3月前', '左侧后交通动脉瘤破裂']) &&
           includesAny(pi, ['SAH', '蛛网膜下腔出血']);
  },
  case5_denies_headache(output) {
    const obj = parseObj(output); if (!obj) return false;
    // LLM may bundle negations ("否认头晕头痛..."). Check both tokens;
    // proximity isn't safety-critical for a recap field.
    return includesAll(obj.present_illness, ['否认', '头痛']);
  },

  // Case 6 — 复制粘贴冲突
  case6_followup_6m(output) {
    const obj = parseObj(output); if (!obj) return false;
    // LLM may expand to "颈内动脉支架置入术后" (extra 置入). Split the
    // needle so insertions don't break the match.
    const fields = ['auxiliary_exam', 'chief_complaint', 'orders_followup', 'present_illness', 'treatment_plan'];
    return anyFieldIncludesAll(obj, fields, ['支架', '术后', '6', '复查']);
  },
  case6_residual_stenosis(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['残余狭窄<20%', 'TIMI 3']);
  },
  case6_antiplatelet_change(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['3', '停', '波立维', '单抗']);
  },
  case6_asymptomatic(output) {
    const obj = parseObj(output); if (!obj) return false;
    return includesAll(obj.present_illness, ['无头晕', '头痛', '肢体', '无力', '麻木']);
  },
  case6_current_bp(output) {
    const obj = parseObj(output); if (!obj) return false;
    // "（本次）" annotation optional; the 130/78 value is the fact.
    return anyFieldIncludesAll(obj, ['past_history', 'physical_exam', 'present_illness', 'auxiliary_exam'], ['130/78']);
  },
};
