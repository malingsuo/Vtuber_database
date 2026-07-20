// ECharts 按需引入：只註冊用到的圖型與元件，解決整包 1MB 的體積問題
import { use } from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

// 分類色盤（已通過色覺障礙驗證，固定順序、不循環）
export const PALETTE = [
  '#2a78d6', '#1baf7a', '#eda100', '#008300',
  '#4a3aa7', '#e34948', '#e87ba4', '#eb6834',
]

// 通路顏色跟著「通路」這個實體固定，不隨資料多寡改變
export const CHANNEL_META = {
  preorder: { label: '預購', color: '#2a78d6' },
  onsite: { label: '現場', color: '#1baf7a' },
  online: { label: '通販', color: '#eda100' },
}
