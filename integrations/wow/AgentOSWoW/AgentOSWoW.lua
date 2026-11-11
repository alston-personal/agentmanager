-- AgentOS WoW native UI shell for the explicitly supported WoW: Forever API.
-- Important: offline-only at this stage. There is NO installed or trusted bridge.
-- No game automation, filesystem access, direct CLI access or credential storage.
local ADDON_NAME = ...
local panel
local statusLine
local answerLine
local accountLine
local questionBox
local askButton
local function setState(message)
    if statusLine then statusLine:SetText(message) end
end

-- v0.1 outbound read-only status probe. Pixel capture is passive; NEVER
-- interpret a rendered pixel packet as authentication or command authority.
local probeStrip
local probeId = 0
local probeToken = tostring(time()) .. tostring(math.random(100000, 999999))
local PROBE_CELL_SIZE = 4
local PROBE_MAX_CELLS = 200
local function encodeProbe(id, action)
    -- Only known status/account intents. No credentials or realm selector in Lua.
    local payload = '{"action":"' .. action .. '","session":"' .. probeToken .. '"}'
    local length = #payload
    local bytes = {
        0xC7, 0x1A, math.floor(id / 256) % 256, id % 256,
        math.floor(length / 256) % 256, length % 256
    }
    for index = 1, length do bytes[#bytes + 1] = string.byte(payload, index) end
    local s1, s2 = 0, 0
    for index = 3, #bytes do
        s1 = (s1 + bytes[index]) % 255
        s2 = (s2 + s1) % 255
    end
    bytes[#bytes + 1], bytes[#bytes + 2] = s1, s2
    local accumulator, bits, cells = 0, 0, {}
    for _, byte in ipairs(bytes) do
        accumulator = accumulator * 256 + byte
        bits = bits + 8
        while bits >= 3 do
            bits = bits - 3
            cells[#cells + 1] = math.floor(accumulator / (2 ^ bits)) % 8
            accumulator = accumulator % (2 ^ bits)
        end
    end
    if bits > 0 then cells[#cells + 1] = (accumulator * (2 ^ (3 - bits))) % 8 end
    return cells
end

local function ensureProbeStrip()
    if probeStrip then return probeStrip end
    probeStrip = CreateFrame("Frame", nil, UIParent)
    probeStrip:SetFrameStrata("TOOLTIP")
    probeStrip:SetSize(PROBE_CELL_SIZE * PROBE_MAX_CELLS, PROBE_CELL_SIZE)
    probeStrip:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    probeStrip.cells = {}
    for i = 1, PROBE_MAX_CELLS do
        local pixel = probeStrip:CreateTexture(nil, "ARTWORK")
        pixel:SetSize(PROBE_CELL_SIZE, PROBE_CELL_SIZE)
        pixel:SetPoint("TOPLEFT", probeStrip, "TOPLEFT", (i - 1) * PROBE_CELL_SIZE, 0)
        pixel:SetColorTexture(0, 0, 0, 1)
        probeStrip.cells[i] = pixel
    end
    probeStrip:Hide()
    return probeStrip
end

local function emitIntent(action)
    if action ~= "wow.control.status"
       and action ~= "wow.account.login.start"
       and action ~= "wow.account.logout" then
        setState("Unsupported AgentOS action")
        return
    end
    probeId = (probeId % 65535) + 1
    local cells = encodeProbe(probeId, action)
    if #cells > PROBE_MAX_CELLS then
        setState("Status probe too large; no packet sent")
        return
    end
    local strip = ensureProbeStrip()
    for i, texture in ipairs(strip.cells) do
        local cell = cells[i] or 0
        texture:SetColorTexture(
            math.floor(cell / 4) % 2,
            math.floor(cell / 2) % 2,
            cell % 2, 1
        )
    end
    strip:Show()
    setState("Intent " .. action .. " (ID " .. probeId .. "); awaiting verified Bridge")
    if C_Timer and C_Timer.After then
        local sentId = probeId
        C_Timer.After(20, function()
            if probeId == sentId and probeStrip then probeStrip:Hide() end
        end)
    end
end

local function sendStatusProbe()
    emitIntent("wow.control.status")
end

local function requestAddonLogin()
    -- Game cannot open trusted OAuth itself; Bridge must handle browser pairing.
    emitIntent("wow.account.login.start")
end

local function requestAddonLogout()
    -- This is only a request, never a claim that server-side logout succeeded.
    emitIntent("wow.account.logout")
end

-- Minimal one-shot LoadOnDemand reply slot, installed before game launch.
-- A slot is untrusted until a separately authenticated Windows Bridge
-- publishes the data. This function never authorizes a task.
local replySlotUsed = false
local function safeLabel(text, limit, pattern)
    return type(text) == "string" and #text <= limit
        and string.match(text, pattern) ~= nil
end

local function loadStatusReplySlot()
    if probeId == 0 then setState("Send a status probe first"); return end
    if replySlotUsed then setState("Reply slot spent; /reload before another read"); return end
    replySlotUsed = true
    local loader = (C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn
    if type(loader) ~= "function" then setState("Reply slot API unavailable"); return end
    local ok = loader("AgentOSWoW_R001")
    if not ok then setState("Reply slot unavailable; compatible client required"); return end
    local data = AgentOSWoWReplySlot
    AgentOSWoWReplySlot = nil
    if type(data) == "table" and data.schema == "agentos.wow.account.reply/v1" then
        if type(data.request_id) ~= "number" or data.request_id ~= probeId
            or type(data.signed_in) ~= "boolean"
            or (data.status ~= "PAIRING_STARTED" and data.status ~= "SIGNED_IN"
                and data.status ~= "SIGNED_OUT" and data.status ~= "REVOCATION_UNCONFIRMED"
                and data.status ~= "REALM_SELECTED")
            or (data.signed_in and (not safeLabel(data.account, 128, "^[%w@%._%+%-]+$")
                or (data.realm ~= nil and not safeLabel(data.realm, 70, "^[%w%-]+$"))))
            or (not data.signed_in and (data.account ~= nil or data.realm ~= nil)) then
            setState("Account reply missing or invalid")
            return
        end
        if accountLine then
            if data.signed_in then
                accountLine:SetText("Addon account: " .. data.account .. " | Realm: " .. (data.realm or "none"))
            else
                accountLine:SetText("Addon account: not signed in | Realm: none")
            end
        end
        setState("Account display reply read; ONE verification still requires Bridge")
        return
    end
    if type(data) ~= "table"
        or data.schema ~= "agentos.wow.status.reply/v1"
        or type(data.request_id) ~= "number"
        or data.request_id ~= probeId
        or (data.state ~= nil and not safeLabel(data.state, 64, "^[%w_%-]+$"))
        or (data.paw ~= nil and not safeLabel(data.paw, 64, "^[%w_%-]+$"))
        or (data.receipt ~= nil and data.receipt ~= false
            and not safeLabel(data.receipt, 128, "^[%w_%.:%-]+$")) then
        setState("Reply missing, stale or rejected")
        return
    end
    if answerLine then
        answerLine:SetText("State: " .. (data.state or "unknown") ..
            " | Paw: " .. (data.paw or "unknown") ..
            " | Receipt: " .. ((data.receipt == false and "none") or data.receipt or "none"))
    end
    setState("Local reply slot decoded; live ONE verification pending")
end

local function createPanel()
    if panel then return panel end
    panel = CreateFrame("Frame", "AgentOSWoWPanel", UIParent, "BackdropTemplate")
    panel:SetSize(445, 390)
    panel:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    panel:SetMovable(true)
    panel:EnableMouse(true)
    panel:RegisterForDrag("LeftButton")
    panel:SetScript("OnDragStart", panel.StartMoving)
    panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
    panel:SetBackdrop({
        bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = true, tileSize = 16, edgeSize = 16,
        insets = {left = 4, right = 4, top = 4, bottom = 4},
    })
    panel:SetBackdropColor(0.04, 0.08, 0.14, 0.96)
    local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", panel, "TOPLEFT", 16, -17)
    title:SetText("AgentOS")
    local close = CreateFrame("Button", nil, panel, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -4, -3)
    statusLine = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    statusLine:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -23)
    statusLine:SetWidth(400)
    statusLine:SetJustifyH("LEFT")
    statusLine:SetText("Bridge: not connected | ONE: unknown")
    accountLine = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    accountLine:SetPoint("TOPLEFT", statusLine, "BOTTOMLEFT", 0, -14)
    accountLine:SetWidth(400)
    accountLine:SetJustifyH("LEFT")
    accountLine:SetText("Addon account: not signed in | Realm: none")
    local label = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    label:SetPoint("TOPLEFT", accountLine, "BOTTOMLEFT", 0, -18)
    label:SetText("Ask AgentOS (read-only; not available until bridge approval)")
    questionBox = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
    questionBox:SetSize(383, 32)
    questionBox:SetPoint("TOPLEFT", label, "BOTTOMLEFT", 7, -10)
    questionBox:SetAutoFocus(false)
    questionBox:SetMaxLetters(500)
    questionBox:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    questionBox:Disable()
    askButton = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    askButton:SetSize(110, 28)
    askButton:SetPoint("TOPLEFT", questionBox, "BOTTOMLEFT", -7, -18)
    askButton:SetText("Send (disabled)")
    askButton:Disable()
    answerLine = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    answerLine:SetWidth(400)
    answerLine:SetJustifyH("LEFT")
    answerLine:SetPoint("TOPLEFT", askButton, "BOTTOMLEFT", 0, -17)
    answerLine:SetText("No live data. The AgentOS local Bridge is not installed or verified.")
    local probe = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    probe:SetSize(128, 28)
    probe:SetPoint("LEFT", askButton, "RIGHT", 14, 0)
    probe:SetText("Status probe")
    probe:SetScript("OnClick", sendStatusProbe)
    local readSlot = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    readSlot:SetSize(160, 26)
    readSlot:SetPoint("TOPLEFT", answerLine, "BOTTOMLEFT", 0, -18)
    readSlot:SetText("Read reply slot (once)")
    readSlot:SetScript("OnClick", loadStatusReplySlot)
    local login = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    login:SetSize(175, 27)
    login:SetPoint("TOPLEFT", readSlot, "BOTTOMLEFT", 0, -16)
    login:SetText("Sign in via Bridge")
    login:SetScript("OnClick", requestAddonLogin)
    local logout = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    logout:SetSize(175, 27)
    logout:SetPoint("LEFT", login, "RIGHT", 12, 0)
    logout:SetText("Sign out via Bridge")
    logout:SetScript("OnClick", requestAddonLogout)
    -- A click only emits a request; no authenticated user or Realm is
    -- displayed until a separately verified host Bridge supplies that state.
    panel:Hide()
    return panel
end
SLASH_AGENTOSWOW1 = "/agentos"
SlashCmdList.AGENTOSWOW = function(command)
    local p = createPanel()
    if p:IsShown() then p:Hide()
    else
        p:Show()
        setState("Bridge: not connected | ONE: unknown")
    end
end
-- No transport handler here by design. Never display 'connected' without verified
-- Node-side session freshness + authorized ONE status evidence.
