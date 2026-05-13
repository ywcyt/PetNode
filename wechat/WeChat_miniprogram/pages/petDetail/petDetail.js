Page({
  data: {
    petId: null,
    // 地图中心点坐标 (假设在某个公园)
    latitude: 29.5630, // 重庆的纬度
    longitude: 106.4600, // 重庆的经度
    // 地图上的狗子标记点
    markers: [],
    
    // 健康图表配置数据
    healthCharts: [
      {
        id: 'steps',
        title: '步数',
        unit: '步',
        average: '8,925',
        color: '#007aff', // 蓝色
        // 模拟过去7天的数据高度比例 (0-100%)
        dataPoints: [60, 30, 50, 20, 45, 65, 5], 
        summary: '今年你一天走的步数与 2025 年大致相同。狗狗整体运动量达标，周三达到了运动峰值，建议周末增加户外互动时间。',
        isExpanded: false // 摘要是否展开的开关
      },
      {
        id: 'heart_rate',
        title: '心跳',
        unit: 'BPM',
        average: '95',
        color: '#ff3b30', // 红色
        dataPoints: [40, 45, 50, 42, 60, 48, 45],
        summary: '心率均值在正常范围内（70-120 BPM）。周二下午有短暂的心率升高，可能与激烈的追逐游戏有关，属于正常生理波动。',
        isExpanded: false
      },
      {
        id: 'respiration',
        title: '呼吸',
        unit: '次/分',
        average: '22',
        color: '#34c759', // 浅绿色
        dataPoints: [30, 28, 35, 30, 32, 29, 30],
        summary: '静息呼吸频率稳定。未检测到异常的急促呼吸，睡眠期间的呼吸曲线非常平滑，显示出极佳的睡眠质量。',
        isExpanded: false
      },
      {
        id: 'temperature',
        title: '体温',
        unit: '°C',
        average: '38.5',
        color: '#ff9500', // 橙色
        dataPoints: [50, 52, 48, 50, 51, 50, 49],
        summary: '体温保持在犬类正常的 38°C - 39°C 之间。未出现发热或体温过低现象，项圈温度传感器工作正常。',
        isExpanded: false
      }
    ]
  },

  onLoad(options) {
    // 1. 获取从首页传过来的狗子 ID
    const currentId = options.id || 1;
    this.setData({ petId: currentId });

    // 2. 调用微信原生 API 获取用户手机的真实位置
    wx.getLocation({
      type: 'gcj02', // 国测局坐标系，微信地图原生的坐标标准
      success: (res) => {
        // 成功获取真实位置后，更新地图中心点
        this.setData({
          latitude: res.latitude,
          longitude: res.longitude
        });
        // 围绕用户的真实位置，生成狗子的坐标
        this.initMockMapData(currentId, res.latitude, res.longitude);
      },
      fail: (err) => {
        console.error("获取位置失败，用户可能拒绝了授权", err);
        // 兜底方案：如果用户拒绝给位置权限，就还是用默认的坐标
        this.initMockMapData(currentId, this.data.latitude, this.data.longitude);
      }
    });
  },

  /**
   * 初始化地图标记点数据 (围绕真实坐标 baseLat, baseLng 散布)
   */
  initMockMapData(currentId, baseLat, baseLng) {
    // 为了模拟真实感，我们在用户真实经纬度上做微小的加减运算（大概偏差几百米）
    const mockMarkers = [
      { id: 1, latitude: baseLat + 0.002, longitude: baseLng + 0.001, iconPath: '/images/DefaultAvatar.png', width: 40, height: 40 },
      { id: 2, latitude: baseLat - 0.003, longitude: baseLng + 0.002, iconPath: '/images/DefaultAvatar.png', width: 30, height: 30, alpha: 0.5 },
      { id: 3, latitude: baseLat + 0.001, longitude: baseLng - 0.003, iconPath: '/images/DefaultAvatar.png', width: 30, height: 30, alpha: 0.5 },
    ];
    
    // 找出当前选中的那只狗，高亮它并加上文字气泡
    const markers = mockMarkers.map(m => {
      if (m.id == currentId) {
        m.width = 50;
        m.height = 50;
        m.alpha = 1;
        m.callout = { 
          content: ' 当前狗狗', 
          color: '#ffffff', 
          bgColor: '#07c160', 
          padding: 5, 
          borderRadius: 5, 
          display: 'ALWAYS' 
        };
      }
      return m;
    });

    this.setData({ markers });
  },
  /**
   * 点击切换摘要的折叠/展开状态
   */
  toggleSummary(e) {
    const key = `healthCharts[${index}].isExpanded`;
    this.setData({
      [key]: !this.data.healthCharts[index].isExpanded
    });
  }, // <--- ⚠️ 核心点1：这里必须有一个逗号，把两个函数隔开！

  /**
   * 点击左上角返回上一页
   */
  goBack() {
    wx.navigateBack({
      delta: 1 // 返回上一级页面
    });
  }

}) // <--- ⚠️ 核心点2：整个 Page 的大括号在这里才真正闭合！
