const API = require('../../utils/api.js');

Page({
  data: {
    petId: null,
    latitude: 29.5630,
    longitude: 106.4600,
    markers: [],
    healthCharts: [],
    loading: true
  },

  async onLoad(options) {
    const petId = options.id;
    if (!petId) {
      wx.showToast({ title: '参数错误', icon: 'error' });
      return;
    }
    this.setData({ petId: petId });
    await this.loadAllData(petId);
  },

  async loadAllData(petId) {
    this.setData({ loading: true });
    try {
      const [location, heartSeries, respSeries, tempSeries] = await Promise.all([
        API.fetchPetLocation(petId).catch(() => null),
        API.fetchHeartRateSeries(petId).catch(() => null),
        API.fetchRespirationSeries(petId).catch(() => null),
        API.fetchTemperatureSeries(petId).catch(() => null)
      ]);

      if (location) {
        this.setData({
          latitude: location.lat || this.data.latitude,
          longitude: location.lng || this.data.longitude
        });
        this.setupMapMarker(petId, location.lat || this.data.latitude, location.lng || this.data.longitude);
      } else {
        this.tryGetPhoneLocation(petId);
      }

      const charts = [];
      if (heartSeries && heartSeries.points && heartSeries.points.length > 0) {
        charts.push(this.buildChart('heart_rate', '心跳', 'BPM', '#ff3b30', heartSeries.points, 'value_bpm'));
      }
      if (respSeries && respSeries.points && respSeries.points.length > 0) {
        charts.push(this.buildChart('respiration', '呼吸', '次/分', '#34c759', respSeries.points, 'value_bpm'));
      }
      if (tempSeries && tempSeries.points && tempSeries.points.length > 0) {
        charts.push(this.buildChart('temperature', '体温', '°C', '#ff9500', tempSeries.points, 'value_celsius'));
      }

      // 如果没有实时数据，显示空状态
      if (charts.length === 0) {
        charts.push({
          id: 'nodata',
          title: '暂无数据',
          unit: '',
          average: '--',
          color: '#999999',
          dataPoints: [10, 10, 10, 10, 10, 10, 10],
          summary: '设备尚未上报健康数据，请确认项圈已佩戴并处于正常工作状态。',
          isExpanded: false
        });
      }

      this.setData({ healthCharts: charts });
    } catch (err) {
      console.error('加载健康数据失败:', err);
    } finally {
      this.setData({ loading: false });
    }
  },

  buildChart(id, title, unit, color, points, valueKey) {
    const sorted = points.slice().sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));
    const values = sorted.map(p => p[valueKey] || 0);
    const daily = this.toDailyBuckets(sorted, valueKey, 7);

    const maxVal = Math.max(...daily, 1);
    const dataPoints = daily.map(v => Math.max(5, Math.round((v / maxVal) * 100)));

    const avg = (daily.reduce((s, v) => s + v, 0) / daily.length).toFixed(1);

    let dateRange = '';
    if (sorted.length > 0 && sorted[0].ts) {
      const first = sorted[0].ts.slice(0, 10);
      const last = sorted[sorted.length - 1].ts.slice(0, 10);
      dateRange = first === last ? first : `${first} - ${last}`;
    }

    return {
      id, title, unit, color,
      average: avg,
      dataPoints,
      summary: `近${daily.length}天平均${avg} ${unit}，最高${maxVal.toFixed(1)} ${unit}。`,
      dateRange,
      isExpanded: false
    };
  },

  toDailyBuckets(sortedPoints, valueKey, maxDays) {
    const buckets = {};
    sortedPoints.forEach(p => {
      const day = (p.ts || '').slice(0, 10);
      if (!buckets[day]) buckets[day] = [];
      buckets[day].push(p[valueKey] || 0);
    });
    const days = Object.keys(buckets).sort();
    const recent = days.slice(-maxDays);
    return recent.map(day => {
      const vals = buckets[day];
      return vals.reduce((s, v) => s + v, 0) / vals.length;
    });
  },

  setupMapMarker(petId, lat, lng) {
    const markers = [{
      id: parseInt(petId) || 1,
      latitude: lat,
      longitude: lng,
      iconPath: '/images/DefaultAvatar.png',
      width: 50,
      height: 50,
      callout: {
        content: ' 当前位置',
        color: '#ffffff',
        bgColor: '#07c160',
        padding: 5,
        borderRadius: 5,
        display: 'ALWAYS'
      }
    }];
    this.setData({ markers });
  },

  tryGetPhoneLocation(petId) {
    wx.getLocation({
      type: 'gcj02',
      success: (res) => {
        this.setData({
          latitude: res.latitude,
          longitude: res.longitude
        });
        this.setupMapMarker(petId, res.latitude, res.longitude);
      },
      fail: () => {
        this.setupMapMarker(petId, this.data.latitude, this.data.longitude);
      }
    });
  },

  toggleSummary(e) {
    const index = e.currentTarget.dataset.index;
    const key = `healthCharts[${index}].isExpanded`;
    this.setData({
      [key]: !this.data.healthCharts[index].isExpanded
    });
  },

  goBack() {
    wx.navigateBack({ delta: 1 });
  }
});
