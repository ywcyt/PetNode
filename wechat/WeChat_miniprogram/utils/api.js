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
          const body = res.data;
          if (body.code === 0) {
            resolve(body.data);
          } else {
            wx.showToast({ title: body.message || '请求失败', icon: 'error' });
            reject(body);
          }
        } else if (res.statusCode === 401) {
          wx.showToast({ title: '登录已过期', icon: 'none' });
          wx.removeStorageSync('access_token');
          wx.reLaunch({ url: '/pages/login/login' });
          reject('Unauthorized');
        } else {
          wx.showToast({ title: (res.data && res.data.message) || '请求失败', icon: 'error' });
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

const qs = (params) => {
  if (!params) return '';
  const keys = Object.keys(params).filter(k => params[k] !== undefined && params[k] !== null);
  if (keys.length === 0) return '';
  return '?' + keys.map(k => `${k}=${encodeURIComponent(params[k])}`).join('&');
};

module.exports = {
  // ===== 微信认证 =====
  wxLoginAndAuth(code) {
    return request('/wechat/auth', 'POST', { code });
  },

  bindWechatUser(data) {
    return request('/wechat/bind', 'POST', data);
  },

  unbindWechat() {
    return request('/wechat/unbind', 'POST');
  },

  // ===== 用户信息 =====
  fetchCurrentUser() {
    return request('/me');
  },

  updateProfile(data) {
    return request('/me', 'PUT', data);
  },

  // ===== 设备管理 =====
  bindDevice(data) {
    return request('/devices/bind', 'POST', data);
  },

  unbindDevice(deviceId) {
    return request(`/devices/${deviceId}/unbind`, 'POST');
  },

  // ===== 宠物列表与详情 =====
  fetchPets() {
    return request('/pets');
  },

  fetchPetSummary(petId) {
    return request(`/pets/${petId}/summary`);
  },

  updatePet(petId, data) {
    return request(`/pets/${petId}`, 'PUT', data);
  },

  // ===== 健康数据 =====
  fetchRespirationLatest(petId) {
    return request(`/pets/${petId}/respiration/latest`);
  },

  fetchRespirationSeries(petId, params = {}) {
    return request(`/pets/${petId}/respiration/series${qs(params)}`);
  },

  fetchHeartRateLatest(petId) {
    return request(`/pets/${petId}/heart-rate/latest`);
  },

  fetchHeartRateSeries(petId, params = {}) {
    return request(`/pets/${petId}/heart-rate/series${qs(params)}`);
  },

  fetchTemperatureSeries(petId, params = {}) {
    return request(`/pets/${petId}/temperature/series${qs(params)}`);
  },

  // ===== 定位 =====
  fetchPetLocation(petId) {
    return request(`/pets/${petId}/location/latest`);
  },

  // ===== 事件/告警 =====
  fetchPetEvents(petId, params = {}) {
    return request(`/pets/${petId}/events${qs(params)}`);
  },

  markEventRead(petId, eventId) {
    return request(`/pets/${petId}/events/${eventId}/read`, 'PUT');
  },

  // ===== 家庭组 =====
  createFamily() {
    return request('/family', 'POST');
  },

  inviteFamily(expiresIn) {
    return request('/family/invite', 'POST', { expires_in: expiresIn });
  },

  joinFamily(inviteToken) {
    return request('/family/join', 'POST', { invite_token: inviteToken });
  },

  fetchFamilyMembers() {
    return request('/family/members');
  },

  removeFamilyMember(userId) {
    return request(`/family/members/${userId}`, 'DELETE');
  }
};
