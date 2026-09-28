import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count >= 2 else {
    fputs("usage: macos_vision_ocr <image>\n", stderr)
    exit(2)
}
let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path) else {
    fputs("image_load_failed\n", stderr)
    exit(3)
}
var proposed = CGRect(origin: .zero, size: image.size)
guard let cg = image.cgImage(forProposedRect: &proposed, context: nil, hints: nil) else {
    fputs("cgimage_failed\n", stderr)
    exit(4)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hant", "en-US", "zh-Hans"]
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("vision_failed\n", stderr)
    exit(5)
}
let observations = request.results ?? []
for observation in observations {
    if let candidate = observation.topCandidates(1).first {
        print(candidate.string.replacingOccurrences(of: "\n", with: " "))
    }
}
