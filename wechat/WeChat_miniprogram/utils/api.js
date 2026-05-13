const BASE_URL = 'http://127.0.0.1:5000/api/v1'; 

const request = (url, method = 'GET', data = {}) => {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('access_token'); 
    wx.request({
      url: BASE_URL + url,
      method: method,
      data: data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '' 
      },
      success: (res) => {
        if (res.statusCode === 200 || res.statusCode === 201) {
          resolve(res.data);
        } else if (res.statusCode === 401) {
          wx.showToast({ title: '登录已过期', icon: 'none' });
          wx.reLaunch({ url: '/pages/login/login' });
          reject('Unauthorized');
        } else {
          wx.showToast({ title: res.data.message || '请求失败', icon: 'error' });
          reject(res.data);
        }
      },
      fail: (err) => {
        wx.showToast({ title: '网络异常', icon: 'error' });
        reject(err);
      }
    });
  });
};

// utils/api.js 里的临时修改
module.exports = {
  wxLoginAndAuth: (code) => {
    // 暂时不发网络请求，直接假装服务器返回了
    return new Promise((resolve) => {
      console.log("正在使用 Mock 数据登录...");
      resolve({
        is_bound: false, // 假装是新用户，先看看能不能跳到绑定页
        wx_identity_token: 'mock_token_123456'
      });
    });
  },
  fetchCurrentUser: () => {
    return new Promise((resolve) => {
      resolve({ nickname: '测试用户', user_id: 1 });
    });
  }
};