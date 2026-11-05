// Container-only worker. No external crates, network, dynamic paths or flags.
use std::process::{Command, Stdio};

#[derive(Clone, Copy)]
pub struct Response { pub status: u16, pub body: &'static str }
#[path = "/fixture/alpha/authz.rs"] mod alpha;
#[path = "/fixture/beta/authz.rs"] mod beta;
#[path = "/fixture/gamma/authz.rs"] mod gamma;
#[path = "/fixture/delta/authz.rs"] mod delta;

type Reader = fn(&str, &str) -> Response;
const CASES: [(&str, &str, &str); 5] = [
    ("case-01", "alice", "record-bob"),
    ("case-02", "bob", "record-bob"),
    ("case-03", "alice", "record-alice"),
    ("case-04", "guest", "record-bob"),
    ("case-05", "alice", "record-missing"),
];

fn reader(variant: &str) -> Option<Reader> {
    match variant {
        "alpha" => Some(alpha::read_record), "beta" => Some(beta::read_record),
        "gamma" => Some(gamma::read_record), "delta" => Some(delta::read_record),
        _ => None,
    }
}

fn valid_shape(response: Response) -> bool {
    (100..=599).contains(&response.status) && response.body.len() <= 256
        && response.body.starts_with('{') && response.body.ends_with('}')
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).take(3).collect();
    if args.len() != 2 || args[0] != "rust-cargo-test" || reader(&args[1]).is_none() {
        println!("{{\"schema_version\":\"worker-observation-1\",\"status\":\"invalid-request\"}}");
        std::process::exit(2);
    }
    let variant = &args[1];
    // Paths and flags are trusted constants, not model-selected strings. The
    // entire worker/process tree still requires the independent container limit.
    let tested = Command::new("/usr/local/cargo/bin/cargo")
        .args(["test", "--offline", "--locked", "--quiet", "--manifest-path", "/worker/Cargo.toml",
               "--target-dir", "/output/cargo-target", "--", "--exact", "tests::response_shapes"])
        .env_clear()
        .env("PATH", "/usr/local/cargo/bin:/usr/local/bin:/usr/bin:/bin")
        .env("HOME", "/scratch")
        .env("CARGO_HOME", "/usr/local/cargo")
        .env("RUSTUP_HOME", "/usr/local/rustup")
        .env("CARGO_NET_OFFLINE", "true")
        .env("TMPDIR", "/scratch")
        .env("LABPROOF_VARIANT", variant)
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
        .status().map(|status| status.success()).unwrap_or(false);
    let selected = reader(variant).unwrap();
    let responses: Vec<Response> = CASES.iter().map(|(_, actor, record)| selected(actor, record)).collect();
    let success = tested && responses.iter().copied().all(valid_shape);
    let observations: Vec<String> = if success {
        CASES.iter().zip(responses.iter()).map(|((id, _, _), response)| {
            format!("{{\"case_id\":\"{}\",\"response\":{{\"status\":{},\"body\":{}}}}}",
                    id, response.status, response.body)
        }).collect()
    } else { Vec::new() };
    println!("{{\"schema_version\":\"worker-observation-1\",\"operation_id\":\"rust-cargo-test\",\"variant\":\"{}\",\"tool\":\"cargo\",\"tool_version\":\"{}\",\"status\":\"{}\",\"exit_code\":{},\"timed_out\":false,\"truncated\":false,\"observations\":[{}]}}",
             variant, include_str!("/worker/cargo-version.txt").trim(), if success { "completed" } else { "tool-error" },
             if success { 0 } else { 1 }, observations.join(","));
    if !success { std::process::exit(1); }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn response_shapes() {
        // Public shape test only. Evaluator oracle and semantic labels are absent.
        let variant = std::env::var("LABPROOF_VARIANT").expect("fixed variant required");
        let selected = reader(&variant).expect("opaque variant required");
        for (_, actor, record) in CASES {
            assert!(valid_shape(selected(actor, record)));
        }
    }
}
