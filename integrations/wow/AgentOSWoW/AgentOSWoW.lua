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
-- Candidate data-only AI answer response: never authorizes commands.
-- A future question transport must set this ID from an actual player question.
local expectedAIRequestId = nil
local function validAIRequestId(value)
    return type(value) == "string" and #value >= 1 and #value <= 64
        and value:match("^[%w][%w%.%_:%-]*$") ~= nil
end
local function handleCompanionAnswer(data)
    -- No question transport is installed yet: fail closed, not a fabricated
    -- answer or user identity. Other AddOns cannot grant trusted Bridge status.
    if not validAIRequestId(expectedAIRequestId)
        or type(data.request_id) ~= "string"
        or data.request_id ~= expectedAIRequestId
        or data.schema ~= "agentos.wow.companion.reply/v1"
        or data.action ~= "ui.answer"
        or (data.category ~= "general" and data.category ~= "npc"
            and data.category ~= "quest" and data.category ~= "location")
        or type(data.answer) ~= "string"
        or #data.answer < 1 or #data.answer > 1200
        or data.answer:find("|", 1, true) then
        expectedAIRequestId = nil
        setState("AI reply rejected: no matching authorized question")
        return
    end
    for i = 1, #data.answer do
        local ch = data.answer:byte(i)
        if ch < 32 and ch ~= 9 and ch ~= 10 then
            expectedAIRequestId = nil
            setState("AI reply rejected: invalid text")
            return
        end
    end
    -- Make the request one-shot even if UI is called again.
    expectedAIRequestId = nil
    if answerLine then answerLine:SetText(data.answer) end
    setState("AI text reply displayed; model/game facts not independently verified")
end

-- Diagnostic-only candidate multipart question display. The player explicitly
-- stages a question and advances ONE RGB frame per click. No automatic retries,
-- hidden time-based stepping, command execution, or claim of Bridge receipt.
-- All frames use the same existing 200-cell screen-strip transport format.
local stagedQuestionFrames = nil
local stagedFrameIndex = 0
local nextFrameButton
local QUESTION_CHUNK_BYTES = 54
local QUESTION_MAX_BYTES = 500
local QUESTION_MAX_PARTS = 16
local function encodeRawFrame(id, payload)
    if type(payload) ~= "string" or #payload < 1 or #payload > 67 then return nil end
    local bytes = {0xC7, 0x1A, math.floor(id / 256) % 256, id % 256,
                   math.floor(#payload / 256) % 256, #payload % 256}
    for i = 1, #payload do bytes[#bytes + 1] = payload:byte(i) end
    local a, b = 0, 0
    for i = 3, #bytes do
        a = (a + bytes[i]) % 255
        b = (b + a) % 255
    end
    bytes[#bytes + 1] = a
    bytes[#bytes + 1] = b
    local acc, bits, cells = 0, 0, {}
    for _, byte in ipairs(bytes) do
        acc = acc * 256 + byte
        bits = bits + 8
        while bits >= 3 do
            bits = bits - 3
            cells[#cells + 1] = math.floor(acc / (2 ^ bits)) % 8
            acc = acc % (2 ^ bits)
        end
    end
    if bits > 0 then cells[#cells + 1] = (acc * (2 ^ (3 - bits))) % 8 end
    if #cells > PROBE_MAX_CELLS then return nil end
    return cells
end
local function bytePair(n)
    return string.char(math.floor(n / 256) % 256, n % 256)
end
local function stageDiagnosticQuestion()
    if not questionBox then return end
    local question = questionBox:GetText()
    if type(question) ~= "string" or #question < 1 or #question > QUESTION_MAX_BYTES
       or question:find("|", 1, true) then
        setState("Invalid question; 1-500 UTF-8 bytes, no game markup")
        return
    end
    for i = 1, #question do
        local ch = question:byte(i)
        if ch < 32 and ch ~= 9 and ch ~= 10 then
            setState("Invalid question controls")
            return
        end
    end
    local total = math.ceil(#question / QUESTION_CHUNK_BYTES)
    if total < 1 or total > QUESTION_MAX_PARTS then
        setState("Question too long for diagnostic frames")
        return
    end
    probeId = (probeId % 65535) + 1
    local id = probeId
    -- Eight bytes used only for correlation. NOT cryptographic authorization.
    local session = ""
    for i = 1, 8 do session = session .. string.char(math.random(0, 255)) end
    local frames = {}
    for index = 0, total - 1 do
        local part = question:sub(index * QUESTION_CHUNK_BYTES + 1,
                                  (index + 1) * QUESTION_CHUNK_BYTES)
        local payload = string.char(0xA1) .. session .. bytePair(id)
                        .. string.char(index, total) .. part
        local cells = encodeRawFrame(id, payload)
        if not cells then
            setState("Unable to stage diagnostic frame")
            return
        end
        frames[#frames + 1] = cells
    end
    stagedQuestionFrames = frames
    stagedFrameIndex = 0
    expectedAIRequestId = "ask-" .. tostring(id)
    if nextFrameButton then nextFrameButton:Enable() end
    setState("Question staged locally (" .. total .. " parts). Not sent; Bridge unverified")
end
local function displayNextDiagnosticFrame()
    if not stagedQuestionFrames then
        setState("Stage a question first")
        return
    end
    if stagedFrameIndex >= #stagedQuestionFrames then
        setState("No more frames; host receipt NOT verified")
        return
    end
    local strip = ensureProbeStrip()
    local cells = stagedQuestionFrames[stagedFrameIndex + 1]
    for i, texture in ipairs(strip.cells) do
        local cell = cells[i] or 0
        texture:SetColorTexture(math.floor(cell / 4) % 2,
                                math.floor(cell / 2) % 2, cell % 2, 1)
    end
    stagedFrameIndex = stagedFrameIndex + 1
    strip:Show()
    setState("Frame " .. stagedFrameIndex .. "/" .. #stagedQuestionFrames
             .. " visible. No Bridge acknowledgment; advance manually")
    if stagedFrameIndex == #stagedQuestionFrames then
        stagedQuestionFrames = nil
        if nextFrameButton then nextFrameButton:Disable() end
    end
end

local function safeLabel(text, limit, pattern)
    return type(text) == "string" and #text <= limit
        and string.match(text, pattern) ~= nil
end

local function loadStatusReplySlot()
    if probeId == 0 and not expectedAIRequestId then setState("Stage a question or send a status probe first"); return end
    if replySlotUsed then setState("Reply slot spent; /reload before another read"); return end
    replySlotUsed = true
    local loader = (C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn
    if type(loader) ~= "function" then setState("Reply slot API unavailable"); return end
    local ok = loader("AgentOSWoW_R001")
    if not ok then setState("Reply slot unavailable; compatible client required"); return end
    local data = AgentOSWoWReplySlot
    AgentOSWoWReplySlot = nil
    if type(data) == "table" and data.schema == "agentos.wow.companion.reply/v1" then
        handleCompanionAnswer(data)
        return
    end
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
    panel:SetSize(445, 435)
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
    label:SetText("AI question diagnostic (frames only; Bridge not connected)")
    questionBox = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
    questionBox:SetSize(383, 32)
    questionBox:SetPoint("TOPLEFT", label, "BOTTOMLEFT", 7, -10)
    questionBox:SetAutoFocus(false)
    questionBox:SetMaxLetters(500)
    questionBox:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    questionBox:Enable()
    askButton = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    askButton:SetSize(110, 28)
    askButton:SetPoint("TOPLEFT", questionBox, "BOTTOMLEFT", -7, -18)
    askButton:SetText("Stage question")
    askButton:SetScript("OnClick", stageDiagnosticQuestion)
    askButton:Enable()
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
    nextFrameButton = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    nextFrameButton:SetSize(167, 27)
    nextFrameButton:SetPoint("TOPLEFT", readSlot, "BOTTOMLEFT", 0, -16)
    nextFrameButton:SetText("Show next frame")
    nextFrameButton:SetScript("OnClick", displayNextDiagnosticFrame)
    nextFrameButton:Disable()
    local login = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    login:SetSize(175, 27)
    login:SetPoint("TOPLEFT", nextFrameButton, "BOTTOMLEFT", 0, -10)
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
