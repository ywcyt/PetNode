const api = require('../../utils/api.js');

Page({
  data: {
    devices: []
  },

  onLoad() {
    this.fetchDevices();
  },

  async fetchDevices() {
    try {
      const data = await api.get('/api/v1/me');
      const pets = data.pets || [];
      this.setData({
        devices: pets.map(p => ({
          id: p.device_id,
          name: p.pet_name || p.device_id,
          collarInfo: `设备 ID: ${p.device_id}`
        }))
      });
    } catch (_) {
      wx.showToast({ title: '设备列表加载失败', icon: 'none' });
    }
  },

  goBack() {
    wx.navigateBack({ delta: 1 });
  },

  unbind(e) {
    const deviceId = e.currentTarget.dataset.id;
    const name = e.currentTarget.dataset.name;
    const that = this;

    wx.showModal({
      title: '解除绑定',
      content: `确定要解除与 ${name} 的项圈绑定吗？此操作不可逆。`,
      confirmColor: '#ff3b30',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await api.post(`/api/v1/devices/${deviceId}/unbind`);
          wx.showToast({ title: '已解绑', icon: 'success' });
          that.fetchDevices();
        } catch (_) {
          wx.showToast({ title: '解绑失败，请重试', icon: 'none' });
        }
      }
    });
  }
});
