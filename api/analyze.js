// Vercel Serverless Function - GMV日报生成器后端代理
export default async function handler(req, res) {
  // CORS
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.status(200).end();
    return;
  }

  if (req.method !== 'POST') {
    return res.status(404).json({ success: false, error: 'Not found' });
  }

  const apiKey = process.env.DASHSCOPE_API_KEY || 'sk-ws-H.RYMLDHE.whau.MEYCIQDquxZlik8DU5m2K0mSSHGKcwkdJPYVXjgO98gGtq3H-QIhAIPwVswRmUE9XKvHpTOzM6LmgqD21SL69VlG5HPH8MLw';

  try {
    const { gmv_image, top10_image } = req.body;

    let report = '';
    // Process GMV image
    if (gmv_image) {
      report = await callDashScope(apiKey, GMV_PROMPT, gmv_image);
    }
    // Process TOP10 image
    if (top10_image) {
      const t10 = await callDashScope(apiKey, TOP10_PROMPT, top10_image);
      if (report) {
        const idx = report.indexOf('今日top10商品：');
        if (idx !== -1) report = report.substring(0, idx) + t10;
        else report += '\n\n' + t10;
      } else {
        report = t10;
      }
    }

    res.status(200).json({ success: true, report });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
}

async function callDashScope(apiKey, prompt, image) {
  const body = {
    model: 'qwen-vl-max',
    messages: [{
      role: 'user',
      content: [
        { type: 'text', text: prompt },
        { type: 'image_url', image_url: { url: image.startsWith('data:') ? image : 'data:image/png;base64,' + image } }
      ]
    }]
  };

  const resp = await fetch('https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + apiKey },
    body: JSON.stringify(body)
  });

  if (!resp.ok) throw new Error('DashScope API 错误 ' + resp.status);
  const data = await resp.json();
  return data.choices[0].message.content.trim();
}

const GMV_PROMPT = `你是一个电商直播数据分析助手。请从这张GMV数据截图中提取信息，严格按照格式输出：

【输出格式】
M月D日

总gmv：总GMV数字（保留两位小数，用逗号分隔千位）

会员开卡/续卡人数：开卡人数/续卡人数（如果截图没有则写"待确认"）

各直播间gmv
（每个直播间占一行，格式：账号名：GMV数字，保留两位小数，用逗号分隔千位）
（必须包含"会员店/会员号"，排在所有直播间第一个；截图中没有的账号不写）

今日top10商品：
1. 商品全名1
2. 商品全名2
...
10. 商品全名10

【重要规则】
- 日期：从截图中识别日期，格式 M.D（如 6.24）
- 总GMV：把所有直播间GMV相加自己计算，不要直接用截图中的"总GMV"
- 直播间列表：只输出截图中出现的直播间，不要预设固定列表，新增的账号也要写上，当天没有的账号不要写，每个直播间独立一行
- 会员店/会员号：如果截图中有这个账号，必须排在第一个；如果没有，则不写
- top10商品：如果截图中没有top10商品信息，则写"今日top10商品：待上传截图"
- 数字格式：保留两位小数，千位用逗号分隔（如 75,936.55）
- 每个字段之间用一个空行分隔`;

const TOP10_PROMPT = `请从这张top10商品截图提取商品名称列表，严格按照以下格式输出：

今日top10商品：
1. 完整的商品名称1（不要截断，尽量还原完整名称）
2. 完整的商品名称2
...
10. 完整的商品名称10

【重要】商品名称必须完整，不要截断。如果名称很长，也要完整输出。`;
