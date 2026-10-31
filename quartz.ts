import { loadQuartzConfig, loadQuartzLayout } from "./quartz/plugins/loader/config-loader"
import { registerCondition } from "./quartz/plugins/loader/conditions"

// Only on the site's top page (used by recent-notes in quartz.config.yaml).
registerCondition("is-index", (props) => props.fileData.slug === "index")

const config = await loadQuartzConfig()
export default config
export const layout = await loadQuartzLayout()
