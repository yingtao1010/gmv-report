/**
 * GMV 日报生成器 - Cloudflare Worker（免费后端代理）
 * 部署步骤：
 * 1. 登录 https://dash.cloudflare.com
 * 2. 左侧菜单 → Workers & Pages → Create → Create Worker
 * 3. 名字填 gmv-report-proxy → Deploy
 * 4. 点击 Edit Code → 把这段代码粘贴进去 → Save and Deploy
 * 5. Settings → Variables → 添加变量 DASHSCOPE_API_KEY = sk-ws-H.RYMLDHE.whau.MEYCIQDquxZlik8DU5m2K0mSSHGKcwkdJPYVXjgO98gGtq3H-QIhAIPwVswRmUE9XKvHpTOzM6LmgqD21SL69VlG5HPH8MLw
 * 6. 部署完成后把 xxx.workers.dev 的网址记下来，填到 index.html 里
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    // 只接受 POST /api/generate
    if (url.pathname !== '/api/generate' || request.method !== 'POST') {
      return jsonResp(404, { success: false, error: 'Not found' });
    }

    const apiKey = env.DASHSCOPE_API_KEY || '';
    if (!apiKey) {
      return jsonResp(500, { success: false, error: 'API Key 未配置' });
    }

    try {
      const body = await request.json();
      const { prompt, image } = body;

      if (!prompt || !image) {
        return jsonResp(400, { success: false, error: '缺少参数 prompt 或 image' });
      }

      // 转发给 DashScope
      const dashscopeBody = {
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
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + apiKey,
        },
        body: JSON.stringify(dashscopeBody),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        return jsonResp(resp.status, { success: false, error: 'DashScope API 错误: ' + resp.status, detail: errText });
      }

      const data = await resp.json();
      const content = data.choices?.[0]?.message?.content || '';

      return jsonResp(200, {
        success: true,
        result: content.trim(),
      });

    } catch (err) {
      return jsonResp(500, { success: false, error: err.message });
    }
  },
};

function jsonResp(status, obj) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
    },
  });
}
