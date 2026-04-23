// (function () {
//     const CACHE_TTL_MS = 30000;
//     const MAX_CACHE_ENTRIES = 200;

//     function patch_link_preview_cache() {
//         if (!window.frappe || !frappe.ui || !frappe.ui.LinkPreview) {
//             return false;
//         }

//         if (frappe.ui.LinkPreview.__amf_preview_cache_patched) {
//             return true;
//         }

//         const preview_cache = {};
//         const inflight_requests = {};
//         const link_preview_prototype = frappe.ui.LinkPreview.prototype;

//         function prune_cache(now) {
//             Object.keys(preview_cache).forEach((cache_key) => {
//                 if (preview_cache[cache_key].expires_at <= now) {
//                     delete preview_cache[cache_key];
//                 }
//             });

//             const cache_keys = Object.keys(preview_cache);
//             if (cache_keys.length <= MAX_CACHE_ENTRIES) {
//                 return;
//             }

//             cache_keys
//                 .sort((left, right) => preview_cache[left].expires_at - preview_cache[right].expires_at)
//                 .slice(0, cache_keys.length - MAX_CACHE_ENTRIES)
//                 .forEach((cache_key) => {
//                     delete preview_cache[cache_key];
//                 });
//         }

//         link_preview_prototype.get_preview_data = function () {
//             const cache_key = [this.doctype, this.name].join("::");
//             const now = Date.now();
//             const cached_entry = preview_cache[cache_key];

//             if (cached_entry && cached_entry.expires_at > now) {
//                 return Promise.resolve(cached_entry.data);
//             }

//             if (cached_entry) {
//                 delete preview_cache[cache_key];
//             }

//             if (inflight_requests[cache_key]) {
//                 return inflight_requests[cache_key];
//             }

//             prune_cache(now);

//             const request = frappe.xcall("frappe.desk.link_preview.get_preview_data", {
//                 doctype: this.doctype,
//                 docname: this.name,
//             });

//             inflight_requests[cache_key] = request.then(
//                 (preview_data) => {
//                     delete inflight_requests[cache_key];

//                     if (preview_data) {
//                         preview_cache[cache_key] = {
//                             data: preview_data,
//                             expires_at: Date.now() + CACHE_TTL_MS,
//                         };
//                     }

//                     return preview_data;
//                 },
//                 (error) => {
//                     delete inflight_requests[cache_key];
//                     throw error;
//                 }
//             );

//             return inflight_requests[cache_key];
//         };

//         frappe.ui.LinkPreview.__amf_preview_cache_patched = true;
//         return true;
//     }

//     if (!patch_link_preview_cache()) {
//         $(patch_link_preview_cache);
//     }
// }());
