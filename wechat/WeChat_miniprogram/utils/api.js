const BASE_URL = 'http://8.156.95.140:5000/api/v1';

const BASE_URL = resolveBaseUrl();

/**
 * 核心请求函数
 * @param {string}  url    - 接口路径 (例如 /api/v1/me)
 * @param {string}  method - GET / POST / PUT / DELETE
 * @param {object}  data   - 请求体（仅 POST/PUT 有效）
 */
const request = (url, method = 'GET', data = {}) => {
  return new Promise((resolve, reject) => {
    const header = {
      'Content-Type': 'application/json'
    };

    const token = wx.getStorageSync('access_token');
    if (token) {
      header['Authorization'] = `Bearer ${token}`;
    }

    const fullUrl = BASE_URL + url;
    console.log(`[API] ${method} ${fullUrl}`, data);

    wx.request({
      url: fullUrl,
      method: method,
      data: data,
      header: header,
      success: (res) => {
        console.log(`[API] ${method} ${url} →`, res.statusCode, res.data);
        const envelope = res.data || {};
        const statusCode = res.statusCode;

        if (statusCode >= 200 && statusCode < 300 && envelope.code === 0) {
          // 成功 → 解包返回 data 字段
          resolve(envelope.data);
        } else if (statusCode === 401 || envelope.code === 40101) {
          // access_token 过期 / 无效
          wx.removeStorageSync('access_token');
          wx.showToast({ title: '登录已过期，请重新登录', icon: 'none' });
          reject(envelope);
        } else if (statusCode === 404) {
          // 404 是可预期的（如未加入家庭），静默失败
          reject(envelope);
        } else {
          // 其他错误：优先用 envelope 中的 message
          const msg = envelope.message || '请求失败';
          wx.showToast({ title: msg, icon: 'none' });
          reject(envelope);
        }
      },
      fail: (err) => {
        console.error(`[API] ${method} ${url} 请求失败:`, err);
        wx.showToast({ title: '网络连接异常，请检查网络', icon: 'none' });
        reject(err);
      }
    });
  });
};

module.exports = {
  BASE_URL,
  get: (url, data) => request(url, 'GET', data),
  post: (url, data) => request(url, 'POST', data),
  put: (url, data) => request(url, 'PUT', data),
  delete: (url, data) => request(url, 'DELETE', data)
};