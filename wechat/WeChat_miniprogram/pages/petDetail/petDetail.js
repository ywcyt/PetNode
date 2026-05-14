const api = require('../../utils/api.js');

Page({
  data: {
    petId: null,
    isRefreshing: false,
    lastFetchTime: '',
    latitude: 29.5630,
    longitude: 106.4600,
    markers: [],
    // 图表数据扁平化，避免嵌套 wx:for diff 问题
    hrAvg: '--', hrDp: [], hrSummary: '加载中...',
    respAvg: '--', respDp: [], respSummary: '加载中...',
    tempAvg: '--', tempDp: [], tempSummary: '加载中...',
    hrExpanded: false, respExpanded: false, tempExpanded: false
  },

  onLoad(options) {
    const petId = options.id || '';
    this.setData({ petId });
    if (!petId) return;
    wx.getLocation({
      type: 'gcj02',
      success: (res) => this.setData({ latitude: res.latitude, longitude: res.longitude })
    });
    this.fetchAllData(petId);
  },

  onShow() {
    if (this.data.petId) {
      this.fetchAllData(this.data.petId);
    }
  },

  async fetchAllData(petId) {
    try {
      const [summary, hrSeries, respSeries, tempSeries, location] = await Promise.all([
        api.get(`/api/v1/pets/${petId}/summary`).catch(() => null),
        api.get(`/api/v1/pets/${petId}/heart-rate/series`, { limit: 7 }).catch(() => null),
        api.get(`/api/v1/pets/${petId}/respiration/series`, { limit: 7 }).catch(() => null),
        api.get(`/api/v1/pets/${petId}/temperature/series`, { limit: 7 }).catch(() => null),
        api.get(`/api/v1/pets/${petId}/location/latest`).catch(() => null)
      ]);

      const now = new Date();
      const timeStr = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
      const patches = { lastFetchTime: timeStr };
      this.applyPatches(patches, summary, hrSeries, respSeries, tempSeries);
      this.setData(patches);

      if (location && location.lat != null) {
        this.setData({
          latitude: location.lat,
          longitude: location.lng,
          markers: [{
            id: 1, latitude: location.lat, longitude: location.lng,
            iconPath: '/images/DefaultAvatar.png', width: 50, height: 50,
            callout: { content: ' 当前宠物位置', color: '#fff', bgColor: '#07c160', padding: 5, borderRadius: 5, display: 'ALWAYS' }
          }]
        });
      }
    } catch (_) {
      wx.showToast({ title: '数据加载失败', icon: 'none' });
    }
  },

  applyPatches(patches, summary, hrSeries, respSeries, tempSeries) {
    const hr = this.buildSeriesData(hrSeries, 'value_bpm');
    patches.hrAvg = summary ? String(Math.round(summary.latest_heart_rate_bpm || 0)) : '--';
    patches.hrDp = hr.dataPoints;
    patches.hrSummary = `心率近${hr.dataPoints.length}次均值 ${Math.round(hr.avg)} BPM，峰值 ${Math.round(hr.maxVal)} BPM`;

    const resp = this.buildSeriesData(respSeries, 'value_bpm');
    patches.respAvg = summary ? String(Math.round(summary.latest_respiration_bpm || 0)) : '--';
    patches.respDp = resp.dataPoints;
    patches.respSummary = `呼吸近${resp.dataPoints.length}次均值 ${Math.round(resp.avg)} 次/分，峰值 ${Math.round(resp.maxVal)} 次/分`;

    const temp = this.buildSeriesData(tempSeries, 'value_celsius');
    patches.tempAvg = temp.dataPoints.length > 0 ? temp.avg.toFixed(1) : '--';
    patches.tempDp = temp.dataPoints;
    patches.tempSummary = `体温近${temp.dataPoints.length}次均值 ${temp.avg.toFixed(1)}°C，峰值 ${temp.maxVal.toFixed(1)}°C`;
  },

  buildSeriesData(series, valueKey) {
    const points = series && series.points ? series.points : [];
    if (points.length === 0) return { dataPoints: [], avg: 0, maxVal: 0 };
    const values = points.map(p => p[valueKey] || 0);
    const maxVal = Math.max(...values, 1);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const dataPoints = values.map((v, i) => ({ id: i, val: Math.round((v / maxVal) * 100) }));
    return { dataPoints, avg, maxVal };
  },

  buildCharts(summary, hrSeries, respSeries, tempSeries) {
    const hr = this.buildSeriesData(hrSeries, 'value_bpm');
    const resp = this.buildSeriesData(respSeries, 'value_bpm');
    const temp = this.buildSeriesData(tempSeries, 'value_celsius');
    const statusText = summary && summary.dog_status
      ? `当前状态：${summary.dog_status}，更新于 ${summary.last_reported_at || '--'}`
      : '暂无数据';

    return [
      {
        id: 'heart_rate', title: '心跳', unit: 'BPM',
        average: summary ? String(Math.round(summary.latest_heart_rate_bpm || 0)) : '--',
        color: '#ff3b30', dataPoints: hr.dataPoints,
        summary: `${statusText}\n心率近${hr.dataPoints.length}次均值 ${Math.round(hr.avg)} BPM，峰值 ${Math.round(hr.maxVal)} BPM。`,
        isExpanded: false
      },
      {
        id: 'respiration', title: '呼吸', unit: '次/分',
        average: summary ? String(Math.round(summary.latest_respiration_bpm || 0)) : '--',
        color: '#34c759', dataPoints: resp.dataPoints,
        summary: `${statusText}\n呼吸近${resp.dataPoints.length}次均值 ${Math.round(resp.avg)} 次/分，峰值 ${Math.round(resp.maxVal)} 次/分。`,
        isExpanded: false
      },
      {
        id: 'temperature', title: '体温', unit: '°C',
        average: temp.dataPoints.length > 0 ? String(temp.avg.toFixed(1)) : '--',
        color: '#ff9500', dataPoints: temp.dataPoints,
        summary: `${statusText}\n体温近${temp.dataPoints.length}次均值 ${temp.avg.toFixed(1)}°C，峰值 ${temp.maxVal.toFixed(1)}°C。`,
        isExpanded: false
      }
    ];
  },

  toggleSummary(e) {
    const idx = e.currentTarget.dataset.index;
    const keys = ['hrExpanded', 'respExpanded', 'tempExpanded'];
    const key = keys[idx];
    if (key) this.setData({ [key]: !this.data[key] });
  },

  async onRefresh() {
    this.setData({ isRefreshing: true });
    try {
      await this.fetchAllData(this.data.petId);
    } finally {
      this.setData({ isRefreshing: false });
    }
  },

  showEditDialog() {
    const that = this;
    wx.showActionSheet({
      itemList: ['修改名称', '修改品种', '查看设备信息'],
      success(res) {
        if (res.tapIndex === 2) {
          wx.showModal({
            title: '设备信息',
            content: `设备 ID：${that.data.petId}`,
            showCancel: false
          });
          return;
        }
        const field = res.tapIndex === 0 ? 'pet_name' : 'breed';
        const label = res.tapIndex === 0 ? '狗狗名字' : '品种';
        // 展示几个预设选项
        const options = res.tapIndex === 0
          ? ['小黄', '旺财', '豆豆', ' Lucky', '布丁']
          : ['金毛', '柯基', '柴犬', '哈士奇', '拉布拉多', '泰迪'];
        wx.showActionSheet({
          itemList: options,
          success: async (r) => {
            const value = options[r.tapIndex];
            try {
              await api.put(`/api/v1/pets/${that.data.petId}`, { [field]: value });
              wx.showToast({ title: `已更新为「${value}」`, icon: 'success' });
            } catch (_) {
              wx.showToast({ title: '修改失败', icon: 'none' });
            }
          }
        });
      }
    });
  },

  goBack() {
    wx.navigateBack({ delta: 1 });
  }
});
